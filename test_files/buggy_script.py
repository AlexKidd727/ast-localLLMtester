#!/usr/bin/env python3
"""
Скрипт для обработки данных пользователей.
Содержит ошибку для тестирования.
"""

import json
from datetime import datetime


def load_users(filepath):
    """Загрузить пользователей из JSON файла."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data.get('users', [])


def filter_active_users(users):
    """Отфильтровать активных пользователей."""
    active = []
    for user in users:
        if user['status'] == 'active':
            active.append(user)
    return active


def calculate_average_age(users):
    """Вычислить средний возраст пользователей."""
    total_age = 0
    count = len(users)
    
    for user in users:
        total_age += user['age']
    
    # ОШИБКА: деление на ноль, если users пустой
    average = total_age / count
    return average


def get_oldest_user(users):
    """Найти самого старшего пользователя."""
    if not users:
        return None
    
    oldest = users[0]
    for user in users[1:]:
        if user['age'] > oldest['age']:
            oldest = user
    
    return oldest


def save_report(report, filepath):
    """Сохранить отчёт в JSON файл."""
    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def main():
    """Основная функция."""
    input_file = 'users.json'
    output_file = 'report.json'
    
    # Загрузить пользователей
    users = load_users(input_file)
    
    # Отфильтровать активных
    active_users = filter_active_users(users)
    
    # Вычислить средний возраст
    avg_age = calculate_average_age(active_users)
    
    # Найти самого старшего
    oldest = get_oldest_user(active_users)
    
    # Создать отчёт
    report = {
        'generated_at': datetime.now().isoformat(),
        'total_users': len(users),
        'active_users': len(active_users),
        'average_age': avg_age,
        'oldest_user': oldest
    }
    
    # Сохранить отчёт
    save_report(report, output_file)
    print(f"Отчёт сохранён в {output_file}")


if __name__ == "__main__":
    main()
