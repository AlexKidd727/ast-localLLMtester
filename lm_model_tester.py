# -*- coding: utf-8 -*-
"""
Тестер локальных LLM моделей через LM Studio API.
Настройки подключения задаются через переменные окружения или .env файл.
"""

import os
import requests
import time
import json
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

# Конфигурация (переменные окружения или значения по умолчанию)
LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234")
TEST_FILES_DIR = Path(__file__).parent / "test_files"
RESULTS_DIR = Path(__file__).parent / "results"

# Настройки генерации
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "4096"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.7"))
TOP_P = float(os.environ.get("TOP_P", "0.9"))

# OpenRouter настройки
OPENROUTER_ENABLED = os.environ.get("OPENROUTER_ENABLED", "true").lower() == "true"
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_TOKEN = os.environ.get("OPENROUTER_API_TOKEN", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")

# Промпты для тестов
PYTHON_GENERATION_PROMPT = """
Напиши полноценный Python скрипт, который:
1. Читает CSV файл с данными
2. Фильтрует строки по заданному условию (значение колонки > 100)
3. Вычисляет среднее значение по числовой колонке
4. Сохраняет результат в JSON файл
5. Добавь обработку ошибок и логирование

Код должен быть готов к запуску, с импортами и примером использования.
"""

# Тестовые данные
TEST_DATA = {
    "generation": {
        "name": "Генерация Python файла",
        "prompt": PYTHON_GENERATION_PROMPT,
        "output_file": TEST_FILES_DIR / "generated_script.py"
    },
    "fix_error": {
        "name": "Исправление ошибки в Python файле",
        "input_file": TEST_FILES_DIR / "buggy_script.py",
        "error_log_file": TEST_FILES_DIR / "error_log.txt",
        "output_file": TEST_FILES_DIR / "fixed_script.py"
    }
}


def get_models() -> list[dict]:
    """Получить список всех моделей с сервера LM Studio."""
    print(f"Подключение к {LM_STUDIO_BASE_URL}...")
    try:
        response = requests.get(f"{LM_STUDIO_BASE_URL}/v1/models", timeout=30)
        response.raise_for_status()
        data = response.json()
        models = data.get("data", [])
        print(f"Найдено моделей: {len(models)}")
        return models
    except requests.exceptions.RequestException as e:
        print(f"Ошибка подключения: {e}")
        return []


def unload_model(model_id: str) -> bool:
    """Выгрузить модель из памяти."""
    try:
        response = requests.post(
            f"{LM_STUDIO_BASE_URL}/api/v0/models/{model_id}/unload",
            timeout=30
        )
        if response.status_code in (200, 204):
            print(f"  Модель {model_id} выгружена")
            return True
        else:
            print(f"  Не удалось выгрузить модель {model_id}: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"  Ошибка выгрузки модели: {e}")
        return False


def evaluate_code(code: str, task_type: str) -> Optional[dict]:
    """
    Оценить сгенерированный код через OpenRouter.
    Возвращает оценку и комментарии.
    """
    if not OPENROUTER_ENABLED or not OPENROUTER_API_TOKEN:
        return None
    
    prompt = f"""Оцени следующий Python код по шкале от 1 до 10.
Критерии: отсутствие ошибок, эффективность, читаемость, соответствие задаче.

Задача: {task_type}

Код:
```python
{code}
```

Ответь в формате JSON:
{{
    "score": число от 1 до 10,
    "errors": ["список ошибок или пустой массив"],
    "comments": "краткие комментарии по улучшению"
}}
"""
    
    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_TOKEN}",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000,
                "temperature": 0.3
            },
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Извлечь JSON из ответа
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                eval_data = json.loads(json_match.group())
                return {
                    "score": eval_data.get("score", 0),
                    "errors": eval_data.get("errors", []),
                    "comments": eval_data.get("comments", ""),
                    "model": OPENROUTER_MODEL
                }
        else:
            print(f"  Ошибка оценки: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"  Ошибка оценки кода: {e}")
    
    return None


def extract_params_count(model_name: str) -> int:
    """Извлечь количество параметров из названия модели."""
    # Паттерны для поиска количества параметров (7b, 13b, 70b, 1.5b, etc.)
    patterns = [
        r'(\d+(?:\.\d+)?)[bB]',  # 7b, 13b, 1.5b
        r'(\d+(?:\.\d+)?)[_\-]?billion',  # 7_billion
        r'(\d+(?:\.\d+)?)[_\-]?b',  # 7_b
    ]
    
    for pattern in patterns:
        match = re.search(pattern, model_name, re.IGNORECASE)
        if match:
            return int(float(match.group(1)) * 1_000_000_000)
    
    # Если не найдено, возвращаем 0 для сортировки в начале
    return 0


def sort_models_by_params(models: list[dict]) -> list[dict]:
    """Отсортировать модели по количеству параметров (возрастание)."""
    def get_sort_key(model: dict) -> tuple[int, str]:
        model_id = model.get("id", model.get("name", ""))
        params = extract_params_count(model_id)
        return (params, model_id)
    
    return sorted(models, key=get_sort_key)


def check_model_ready(model_id: str, timeout: int = 300, poll_interval: int = 5) -> bool:
    """
    Проверить, что модель готова отвечать.
    Отправляет простой запрос и ждёт ответа.
    """
    print(f"  Проверка готовности модели '{model_id}'...")
    
    start_time = time.time()
    simple_prompt = "Ответь одним словом: готов"
    
    while time.time() - start_time < timeout:
        try:
            response = requests.post(
                f"{LM_STUDIO_BASE_URL}/v1/chat/completions",
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": simple_prompt}],
                    "max_tokens": 50,
                    "temperature": 0.1
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                message = result.get("choices", [{}])[0].get("message", {})
                content = message.get("content", "")
                reasoning = message.get("reasoning_content", "")
                
                if content.strip() or reasoning.strip():
                    print(f"  Модель готова (content: '{content.strip()[:50]}', reasoning: '{reasoning.strip()[:50]}')")
                    return True
                    
        except requests.exceptions.RequestException as e:
            print(f"  Ошибка: {e}")
        
        print(f"  Ожидание загрузки модели... ({int(time.time() - start_time)}с)")
        time.sleep(poll_interval)
    
    print(f"  Таймаут ожидания готовности модели")
    return False


def measure_response_time(
    model_id: str,
    prompt: str,
    endpoint: str = "/v1/chat/completions",
    **kwargs
) -> Optional[dict]:
    """
    Измерить время ответа модели.
    Возвращает dict с результатами или None при ошибке.
    """
    start_time = time.time()
    
    try:
        if endpoint == "/v1/chat/completions":
            payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get("max_tokens", MAX_TOKENS),
                "temperature": kwargs.get("temperature", TEMPERATURE),
                "top_p": kwargs.get("top_p", TOP_P),
                "stream": False
            }
        elif endpoint == "/v1/completions":
            payload = {
                "model": model_id,
                "prompt": prompt,
                "max_tokens": kwargs.get("max_tokens", MAX_TOKENS),
                "temperature": kwargs.get("temperature", TEMPERATURE),
                "top_p": kwargs.get("top_p", TOP_P),
                "stream": False
            }
        else:
            payload = {"model": model_id, "input": prompt}
        
        response = requests.post(
            f"{LM_STUDIO_BASE_URL}{endpoint}",
            json=payload,
            timeout=1200  # 20 минут на генерацию
        )
        response.raise_for_status()
        
        elapsed_time = time.time() - start_time
        result = response.json()
        
        # Извлечь ответ в зависимости от endpoint
        content = ""
        if endpoint == "/v1/chat/completions":
            message = result.get("choices", [{}])[0].get("message", {})
            content = message.get("content", "")
            reasoning = message.get("reasoning_content", "")
            # Для reasoning моделей - использовать reasoning как контент
            if not content.strip() and reasoning.strip():
                content = reasoning
        elif endpoint == "/v1/completions":
            content = result.get("choices", [{}])[0].get("text", "")
        
        return {
            "success": True,
            "elapsed_time": elapsed_time,
            "content": content,
            "response_data": result
        }
        
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Timeout",
            "elapsed_time": time.time() - start_time
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "elapsed_time": time.time() - start_time
        }


def test_python_generation(model_id: str) -> dict:
    """Тест: генерация Python файла по описанию."""
    print(f"  Тест: Генерация Python файла...")
    
    # Создать папку для результатов модели
    model_dir = RESULTS_DIR / model_id.replace("/", "_")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    result = measure_response_time(
        model_id=model_id,
        prompt=TEST_DATA["generation"]["prompt"],
        endpoint="/v1/chat/completions",
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        top_p=TOP_P
    )
    
    if result and result["success"]:
        # Сохранить сгенерированный код
        output_file = model_dir / "generated_script.py"
        
        # Попытаться извлечь код из ответа
        content = result["content"]
        code_match = re.search(r'```python\s*(.*?)\s*```', content, re.DOTALL)
        if code_match:
            content = code_match.group(1)
        
        output_file.write_text(content, encoding="utf-8")
        print(f"  Результат сохранён в: {output_file}")
        
        # Оценить код через OpenRouter
        print(f"  Оценка кода...")
        evaluation = evaluate_code(content, "Генерация Python скрипта для обработки CSV")
        if evaluation:
            result["evaluation"] = evaluation
            print(f"  Оценка: {evaluation['score']}/10")
    
    return result


def test_fix_error(model_id: str) -> dict:
    """Тест: исправление ошибки в Python файле по логу."""
    input_file = TEST_DATA["fix_error"]["input_file"]
    error_log_file = TEST_DATA["fix_error"]["error_log_file"]
    
    # Создать папку для результатов модели
    model_dir = RESULTS_DIR / model_id.replace("/", "_")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    if not input_file.exists():
        return {"success": False, "error": f"Файл не найден: {input_file}"}
    if not error_log_file.exists():
        return {"success": False, "error": f"Файл не найден: {error_log_file}"}
    
    buggy_code = input_file.read_text(encoding="utf-8")
    error_log = error_log_file.read_text(encoding="utf-8")
    
    prompt = f"""
У меня есть Python код с ошибкой:

```python
{buggy_code}
```

При запуске получается ошибка:
```
{error_log}
```

Исправь код, чтобы ошибка исчезла. Верни только исправленный код без объяснений.
"""
    
    result = measure_response_time(
        model_id=model_id,
        prompt=prompt,
        endpoint="/v1/chat/completions",
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        top_p=TOP_P
    )
    
    if result and result["success"]:
        # Сохранить исправленный код
        output_file = model_dir / "fixed_script.py"
        
        content = result["content"]
        code_match = re.search(r'```python\s*(.*?)\s*```', content, re.DOTALL)
        if code_match:
            content = code_match.group(1)
        
        output_file.write_text(content, encoding="utf-8")
        print(f"  Результат сохранён в: {output_file}")
        
        # Оценить код через OpenRouter
        print(f"  Оценка кода...")
        evaluation = evaluate_code(content, "Исправление ошибки в Python коде")
        if evaluation:
            result["evaluation"] = evaluation
            print(f"  Оценка: {evaluation['score']}/10")
    
    return result


def run_model_tests(model_id: str) -> dict:
    """Запустить все тесты для одной модели."""
    print(f"\n{'='*60}")
    print(f"Тестирование модели: {model_id}")
    print(f"{'='*60}")
    
    # Проверка готовности модели
    if not check_model_ready(model_id):
        return {
            "model": model_id,
            "status": "failed",
            "error": "Модель не готова к тестированию"
        }
    
    results = {
        "model": model_id,
        "status": "completed",
        "tests": {}
    }
    
    # Тест 1: Генерация Python файла
    gen_result = test_python_generation(model_id)
    results["tests"]["generation"] = {
        "name": TEST_DATA["generation"]["name"],
        "success": gen_result.get("success", False),
        "elapsed_time": gen_result.get("elapsed_time", 0),
        "error": gen_result.get("error"),
        "evaluation": gen_result.get("evaluation")
    }
    
    # Тест 2: Исправление ошибки
    fix_result = test_fix_error(model_id)
    results["tests"]["fix_error"] = {
        "name": TEST_DATA["fix_error"]["name"],
        "success": fix_result.get("success", False),
        "elapsed_time": fix_result.get("elapsed_time", 0),
        "error": fix_result.get("error"),
        "evaluation": fix_result.get("evaluation")
    }
    
    return results


def print_results(all_results: list[dict]):
    """Вывести результаты всех тестов в консоль."""
    print(f"\n\n{'='*80}")
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print(f"{'='*80}")
    print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Сервер: {LM_STUDIO_BASE_URL}")
    print(f"{'='*80}\n")
    
    for result in all_results:
        model_id = result.get("model", "Unknown")
        status = result.get("status", "unknown")
        
        print(f"\n📦 Модель: {model_id}")
        print(f"   Статус: {'✅ {status}' if status == 'completed' else f'❌ {status}'}")
        
        if status == "completed":
            tests = result.get("tests", {})
            for test_name, test_data in tests.items():
                success_icon = "✅" if test_data.get("success") else "❌"
                elapsed = test_data.get("elapsed_time", 0)
                error = test_data.get("error")
                
                print(f"   {success_icon} {test_data.get('name', test_name)}")
                print(f"      Время ответа: {elapsed:.2f}с")
                if error:
                    print(f"      Ошибка: {error}")
        else:
            error = result.get("error", "Неизвестная ошибка")
            print(f"   Ошибка: {error}")
    
    # Сводная таблица
    print(f"\n\n{'='*80}")
    print("СВОДНАЯ ТАБЛИЦА")
    print(f"{'='*80}")
    print(f"{'Модель':<50} {'Генерация':<12} {'Исправление':<12} {'Общее время':<12}")
    print(f"{'-'*80}")
    
    for result in all_results:
        model_id = result.get("model", "Unknown")[:48]
        tests = result.get("tests", {})
        
        gen_status = "✅" if tests.get("generation", {}).get("success") else "❌"
        gen_time = tests.get("generation", {}).get("elapsed_time", 0)
        
        fix_status = "✅" if tests.get("fix_error", {}).get("success") else "❌"
        fix_time = tests.get("fix_error", {}).get("elapsed_time", 0)
        
        total_time = gen_time + fix_time
        
        print(f"{model_id:<50} {gen_status} {gen_time:>6.2f}с  {fix_status} {fix_time:>6.2f}с  {total_time:>8.2f}с")
    
    print(f"{'='*80}\n")


def save_results(all_results: list[dict]):
    """Сохранить результаты в JSON файл."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = RESULTS_DIR / f"test_results_{timestamp}.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"Результаты сохранены в: {output_file}")


def main():
    """Основная функция."""
    print("="*60)
    print("LM Studio Model Tester")
    print("="*60)
    
    # Убедиться, что папка test_files существует
    TEST_FILES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Получить список моделей
    models = get_models()
    if not models:
        print("Нет моделей для тестирования. Завершение.")
        return
    
    # Отсортировать по количеству параметров
    sorted_models = sort_models_by_params(models)
    
    print("\nМодели для тестирования (отсортированы по параметрам):")
    for i, model in enumerate(sorted_models, 1):
        model_id = model.get("id", model.get("name", "Unknown"))
        params = extract_params_count(model_id)
        params_str = f"{params/1e9:.1f}B" if params > 0 else "N/A"
        print(f"  {i}. {model_id} ({params_str})")
    
    # Запустить тесты для каждой модели
    all_results = []
    for model in sorted_models:
        model_id = model.get("id", model.get("name", ""))
        if model_id:
            result = run_model_tests(model_id)
            all_results.append(result)
    
    # Вывести результаты
    print_results(all_results)
    
    # Сохранить результаты
    save_results(all_results)


if __name__ == "__main__":
    main()