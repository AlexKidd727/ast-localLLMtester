# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, session
import lm_model_tester as tester
import os
import json
import time
from pathlib import Path
from threading import Thread

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

RESULTS_FILE = Path(__file__).parent / "results.json"

test_status = {}
results_data = {}
running_tests = {}


def load_results():
    """Загрузить результаты из JSON файла при старте."""
    global results_data
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                results_data = json.load(f)
            print(f"Загружено {len(results_data)} результатов из {RESULTS_FILE}")
        except Exception as e:
            print(f"Ошибка загрузки результатов: {e}")
            results_data = {}


def save_results():
    """Сохранить результаты в JSON файл (добавить новые записи)."""
    try:
        RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Читать существующие данные
        existing_data = {}
        if RESULTS_FILE.exists():
            try:
                with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except:
                existing_data = {}
        
        # Объединить с текущими (новые записи перезаписывают старые)
        existing_data.update(results_data)
        
        # Убрать _logged и _timestamp перед сохранением
        data_to_save = {k: {kk: vv for kk, vv in v.items() if kk not in ['_logged', '_timestamp']} for k, v in existing_data.items()}
        
        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        print(f"Результаты сохранены в {RESULTS_FILE}")
    except Exception as e:
        print(f"Ошибка сохранения результатов: {e}")

@app.route('/')
def index():
    """Главная страница с выбором модели"""
    models = tester.get_models()
    if not models:
        return render_template('index.html', error="Нет доступных моделей", models=[], results_data=results_data)
    
    sorted_models = sorted(models, key=lambda m: m['id'])
    
    return render_template(
        'index.html',
        models=sorted_models,
        error=None,
        results_data=results_data
    )

@app.route('/run_test', methods=['POST'])
def run_test():
    """Запустить тест для выбранной модели"""
    data = request.get_json()
    model_id = data.get('model')
    
    if not model_id:
        return jsonify({'error': 'Не указана модель'}), 400
    
    if model_id in running_tests:
        return jsonify({'error': 'Тест для этой модели уже запущен'}), 400
    
    # Удалить только результаты для этой модели (если были)
    global results_data
    if model_id in results_data:
        del results_data[model_id]
    
    # Start test in background thread
    running_tests[model_id] = True
    thread = Thread(target=run_test_in_background, args=(model_id,))
    thread.start()
    
    return jsonify({'status': 'started'})


def run_test_in_background(model_id):
    """Запустить тест в фоновом потоке и обновлять статус"""
    global results_data
    
    print(f"Начат тест для модели: {model_id}")
    
    if model_id in results_data:
        del results_data[model_id]
    
    try:
        results = tester.run_model_tests(model_id)
        results['_logged'] = False
        results['_timestamp'] = time.time()  # Время завершения теста
        results_data[model_id] = results
        print(f"Тест завершён для {model_id}")
        
        # Выгрузить модель после теста
        tester.unload_model(model_id)
        
        # Сохранить результаты
        save_results()
        
    except Exception as e:
        print(f"Ошибка теста для {model_id}: {e}")
        results_data[model_id] = {
            'status': 'failed',
            'error': str(e),
            'tests': {},
            '_logged': False
        }
        save_results()
    finally:
        if model_id in running_tests:
            del running_tests[model_id]


@app.route('/reevaluate', methods=['POST'])
def reevaluate():
    """Перепроверить результат через LLM"""
    data = request.get_json()
    model_id = data.get('model')
    test_type = data.get('test_type')  # 'generation' или 'fix_error'
    
    if not model_id or not test_type:
        return jsonify({'error': 'Не указаны параметры'}), 400
    
    if model_id not in results_data:
        return jsonify({'error': 'Результат не найден'}), 404
    
    try:
        # Получить код из сохраненного файла
        model_dir = tester.RESULTS_DIR / model_id.replace("/", "_")
        
        if test_type == 'generation':
            code_file = model_dir / "generated_script.py"
            task_type = "Генерация Python скрипта для обработки CSV"
        elif test_type == 'fix_error':
            code_file = model_dir / "fixed_script.py"
            task_type = "Исправление ошибки в Python коде"
        else:
            return jsonify({'error': 'Неверный тип теста'}), 400
        
        if not code_file.exists():
            return jsonify({'error': 'Файл с кодом не найден'}), 404
        
        code = code_file.read_text(encoding='utf-8')
        
        # Запустить проверку в фоновом потоке
        thread = Thread(target=reevaluate_in_background, args=(model_id, test_type, code, task_type))
        thread.start()
        
        return jsonify({'status': 'started'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def reevaluate_in_background(model_id, test_type, code, task_type):
    """Перепроверить код в фоновом потоке"""
    global results_data
    
    try:
        print(f"Перепроверка {test_type} для {model_id}...")
        evaluation = tester.evaluate_code(code, task_type)
        
        if evaluation and model_id in results_data:
            results_data[model_id]['tests'][test_type]['evaluation'] = evaluation
            save_results()
            print(f"Перепроверка завершена: {evaluation['score']}/10")
        
    except Exception as e:
        print(f"Ошибка перепроверки: {e}")


@app.route('/get_status')
def get_status():
    """Получить статус тестов"""
    return jsonify({
        'running': list(running_tests.keys()),
        'completed': list(results_data.keys())
    })

@app.route('/get_results')
def get_results():
    """Получить текущие результаты"""
    return jsonify(results_data)

if __name__ == '__main__':
    load_results()
    app.run(debug=True, port=5987, use_reloader=False)