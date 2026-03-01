// JavaScript для управления интерфейсом
let currentTestModel = null;
let loggedModels = new Set();
let lastResultsHash = '';
let evaluationsCache = {}; // Кэш для оценок
let testStartTime = 0; // Время запуска последнего теста

// Сортировка таблицы
let sortColumn = null;
let sortAsc = true;
let currentResultsData = {}; // Хранит текущие данные для сортировки

function sortTable(column) {
    if (sortColumn === column) {
        sortAsc = !sortAsc; // Инвертировать порядок
    } else {
        sortColumn = column;
        sortAsc = true; // По умолчанию по возрастанию
    }
    
    // Обновить заголовки
    document.querySelectorAll('#results-table th').forEach(th => {
        const col = th.getAttribute('data-column');
        if (col === column) {
            th.innerHTML = column === 'model' ? 'Модель ' + (sortAsc ? '↑' : '↓') :
                          column === 'gen_time' ? 'Генерация (с) ' + (sortAsc ? '↑' : '↓') :
                          column === 'gen_score' ? 'Оценка ' + (sortAsc ? '↑' : '↓') :
                          column === 'fix_time' ? 'Исправление (с) ' + (sortAsc ? '↑' : '↓') :
                          column === 'fix_score' ? 'Оценка ' + (sortAsc ? '↑' : '↓') :
                          column === 'total_time' ? 'Общее время (с) ' + (sortAsc ? '↑' : '↓') :
                          'Статус ' + (sortAsc ? '↑' : '↓');
        } else {
            th.innerHTML = th.getAttribute('data-column') === 'model' ? 'Модель ⇅' :
                          th.getAttribute('data-column') === 'gen_time' ? 'Генерация (с) ⇅' :
                          th.getAttribute('data-column') === 'gen_score' ? 'Оценка ⇅' :
                          th.getAttribute('data-column') === 'fix_time' ? 'Исправление (с) ⇅' :
                          th.getAttribute('data-column') === 'fix_score' ? 'Оценка ⇅' :
                          th.getAttribute('data-column') === 'total_time' ? 'Общее время (с) ⇅' :
                          'Статус ⇅';
        }
    });
    
    renderSortedTable();
}

function renderSortedTable() {
    const resultsBody = document.getElementById('results-body');
    if (!resultsBody) return;
    
    const modelIds = Object.keys(currentResultsData).sort((a, b) => {
        let valA, valB;
        
        const resultA = currentResultsData[a];
        const resultB = currentResultsData[b];
        
        switch(sortColumn) {
            case 'model':
                valA = a.toLowerCase();
                valB = b.toLowerCase();
                return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            case 'gen_time':
                valA = resultA.tests?.generation?.elapsed_time || 0;
                valB = resultB.tests?.generation?.elapsed_time || 0;
                break;
            case 'gen_score':
                valA = resultA.tests?.generation?.evaluation?.score || 0;
                valB = resultB.tests?.generation?.evaluation?.score || 0;
                break;
            case 'fix_time':
                valA = resultA.tests?.fix_error?.elapsed_time || 0;
                valB = resultB.tests?.fix_error?.elapsed_time || 0;
                break;
            case 'fix_score':
                valA = resultA.tests?.fix_error?.evaluation?.score || 0;
                valB = resultB.tests?.fix_error?.evaluation?.score || 0;
                break;
            case 'total_time':
                valA = (resultA.tests?.generation?.elapsed_time || 0) + (resultA.tests?.fix_error?.elapsed_time || 0);
                valB = (resultB.tests?.generation?.elapsed_time || 0) + (resultB.tests?.fix_error?.elapsed_time || 0);
                break;
            case 'status':
                valA = resultA.status || '';
                valB = resultB.status || '';
                return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            default:
                return 0;
        }
        
        return sortAsc ? valA - valB : valB - valA;
    });
    
    // Очистить и перерисовать
    resultsBody.innerHTML = '';
    
    for (const modelId of modelIds) {
        const result = currentResultsData[modelId];
        renderResultRow(resultsBody, modelId, result);
    }
}

function renderResultRow(resultsBody, modelId, result) {
    const row = document.createElement('tr');
    let statusIcon = '';
    if (result.status === 'completed') {
        statusIcon = '<span class="status-success">✅</span>';
    } else if (result.status === 'failed') {
        statusIcon = '<span class="status-failed">❌</span>';
    }
    
    const genTime = result.tests?.generation?.elapsed_time || 0;
    const genEval = result.tests?.generation?.evaluation;
    const fixTime = result.tests?.fix_error?.elapsed_time || 0;
    const fixEval = result.tests?.fix_error?.evaluation;
    
    // Сохранить оценки в кэш
    if (genEval) {
        evaluationsCache[modelId + '_gen'] = genEval;
    }
    if (fixEval) {
        evaluationsCache[modelId + '_fix'] = fixEval;
    }
    
    const genScore = genEval ? `<span class="label ${genEval.score >= 7 ? 'label-success' : genEval.score >= 5 ? 'label-warning' : 'label-danger'}" style="cursor:pointer" onclick="showEvalModal('${modelId}', 'Генерация', '${modelId}_gen')">${genEval.score}/10</span>` : `<button class="btn btn-xs btn-default" onclick="reevaluate('${modelId}', 'generation')">Проверить</button>`;
    const fixScore = fixEval ? `<span class="label ${fixEval.score >= 7 ? 'label-success' : fixEval.score >= 5 ? 'label-warning' : 'label-danger'}" style="cursor:pointer" onclick="showEvalModal('${modelId}', 'Исправление ошибки', '${modelId}_fix')">${fixEval.score}/10</span>` : `<button class="btn btn-xs btn-default" onclick="reevaluate('${modelId}', 'fix_error')">Проверить</button>`;
    
    row.innerHTML = `
        <td>${modelId}</td>
        <td>${genTime.toFixed(2)}</td>
        <td>${genScore}</td>
        <td>${fixTime.toFixed(2)}</td>
        <td>${fixScore}</td>
        <td>${(genTime + fixTime).toFixed(2)}</td>
        <td>${statusIcon} ${result.status}</td>
    `;
    
    resultsBody.appendChild(row);
}

function runTest() {
    const modelSelect = document.getElementById('model-select');
    if (modelSelect.value) {
        currentTestModel = modelSelect.value;
        loggedModels.clear(); // Очистить историю логирования
        testStartTime = Date.now() / 1000; // Запомнить время запуска
        
        // Очистить лог перед запуском
        const logElement = document.getElementById('log-content');
        if (logElement) {
            logElement.textContent = '';
        }
        
        updateLog(`🚀 Запуск теста для модели: ${currentTestModel}...`);
        
        fetch('/run_test', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({model: currentTestModel})
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                updateLog(`❌ Ошибка: ${data.error}`);
                currentTestModel = null;
            }
        })
        .catch(err => {
            updateLog(`❌ Ошибка запроса: ${err}`);
            currentTestModel = null;
        });
    } else {
        updateLog('Пожалуйста, выберите модель!');
    }
}

// Обновление лога
function updateLog(content) {
    const logElement = document.getElementById('log-content');
    if (logElement) {
        if (logElement.textContent === 'Ожидание запуска теста...') {
            logElement.textContent = '';
        }
        const timestamp = new Date().toLocaleTimeString();
        logElement.textContent += `[${timestamp}] ${content}` + '\n';
    }
}

// Хеш для сравнения результатов
function hashResults(results) {
    return JSON.stringify(results);
}

// Обновление интерфейса при получении новых данных
function updateInterface() {
    Promise.all([
        fetch('/get_results').then(r => r.json()),
        fetch('/get_status').then(r => r.json())
    ])
    .then(([results, status]) => {
        const resultsBody = document.getElementById('results-body');
        if (!resultsBody) return;
        
        // Проверка: если результаты не изменились - ничего не делаем
        const currentHash = hashResults(results);
        if (currentHash === lastResultsHash && loggedModels.size > 0) {
            return; // Ни лог, ни таблицу не обновляем
        }
        lastResultsHash = currentHash;
        
        // Сохранить данные для сортировки
        currentResultsData = results;
        
        const modelIds = Object.keys(results);
        const runningModels = status.running || [];
        
        if (modelIds.length === 0 && runningModels.length === 0) {
            return;
        }
        
        // Очистить таблицу перед рендерингом
        resultsBody.innerHTML = '';
        
        // Показать запущенные тесты
        for (const modelId of runningModels) {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${modelId}</td>
                <td colspan="3" class="text-center text-info">🔄 Тест выполняется...</td>
                <td>running</td>
            `;
            resultsBody.appendChild(row);
            
            if (currentTestModel === modelId) {
                updateLog(`⏳ Тест выполняется: ${modelId}`);
            }
        }
        
        // Показать завершённые результаты
        for (const modelId of modelIds) {
            const result = results[modelId];
            
            // Проверить timestamp - показывать только результаты текущего теста
            const resultTime = result._timestamp || 0;
            const isNewResult = testStartTime > 0 && resultTime >= testStartTime;
            
            // Добавить лог только если результат новый и модель еще не была залогирована
            if (isNewResult && !loggedModels.has(modelId)) {
                loggedModels.add(modelId);
                updateLog(`📦 Testing model: ${modelId}`);
                updateLog(`   Status: ${result.status === 'completed' ? '✅ Completed' : '❌ Failed'}`);
                
                if (result.tests) {
                    for (const testName in result.tests) {
                        const testRes = result.tests[testName];
                        updateLog(`   ${testName}: ${testRes.success ? '✅ Successful' : '❌ Unsuccessful'}, time: ${testRes.elapsed_time.toFixed(2)}s`);
                    }
                }
                
                if (runningModels.indexOf(modelId) === -1) {
                    currentTestModel = null;
                }
            }
            
            // Добавить строку в таблицу
            const row = document.createElement('tr');
            let statusIcon = '';
            if (result.status === 'completed') {
                statusIcon = '<span class="status-success">✅</span>';
            } else if (result.status === 'failed') {
                statusIcon = '<span class="status-failed">❌</span>';
            }
            
            const genTime = result.tests?.generation?.elapsed_time || 0;
            const genEval = result.tests?.generation?.evaluation;
            const fixTime = result.tests?.fix_error?.elapsed_time || 0;
            const fixEval = result.tests?.fix_error?.evaluation;
            
            // Сохранить оценки в кэш
            if (genEval) {
                evaluationsCache[modelId + '_gen'] = genEval;
            }
            if (fixEval) {
                evaluationsCache[modelId + '_fix'] = fixEval;
            }
        }
        
        // Использовать сортировку если активна
        if (sortColumn) {
            renderSortedTable();
        } else {
            // Иначе просто рендерим по порядку
            for (const modelId of modelIds) {
                const result = results[modelId];
                renderResultRow(resultsBody, modelId, result);
            }
        }
    })
    .catch(err => console.error('Error fetching results:', err));
}

// Показать модальное окно с оценкой
function showEvalModal(modelId, testType, cacheKey) {
    const evaluation = evaluationsCache[cacheKey];
    
    if (!evaluation) {
        alert('Оценка не найдена');
        return;
    }
    
    document.getElementById('modalModel').textContent = modelId;
    document.getElementById('modalTestType').textContent = testType;
    document.getElementById('modalScore').textContent = evaluation.score + '/10';
    
    const errorsList = document.getElementById('modalErrors');
    errorsList.innerHTML = '';
    if (evaluation.errors && evaluation.errors.length > 0) {
        evaluation.errors.forEach(function(err) {
            const li = document.createElement('li');
            li.textContent = err;
            errorsList.appendChild(li);
        });
    } else {
        const li = document.createElement('li');
        li.textContent = 'Нет ошибок';
        li.style.color = 'green';
        errorsList.appendChild(li);
    }
    
    document.getElementById('modalComments').textContent = evaluation.comments || 'Нет комментариев';
    
    // Показать модальное окно
    const modal = document.getElementById('evalModal');
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden'; // Запретить скролл фона
}

// Закрыть модальное окно
function closeEvalModal() {
    const modal = document.getElementById('evalModal');
    modal.style.display = 'none';
    document.body.style.overflow = 'auto'; // Вернуть скролл
}

// Закрытие по клику вне модального окна
document.addEventListener('click', function(e) {
    const modal = document.getElementById('evalModal');
    const modalDialog = document.querySelector('.modal-dialog');
    if (e.target === modal) {
        closeEvalModal();
    }
});

// Перепроверить результат через LLM
function reevaluate(modelId, testType) {
    updateLog(`🔄 Перепроверка ${testType} для ${modelId}...`);
    
    fetch('/reevaluate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({model: modelId, test_type: testType})
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            updateLog(`❌ Ошибка: ${data.error}`);
        } else {
            updateLog(`⏳ Перепроверка запущена...`);
        }
    })
    .catch(err => {
        updateLog(`❌ Ошибка запроса: ${err}`);
    });
}

// Инициализация
window.onload = function() {
    updateInterface();
    setInterval(updateInterface, 2000);
};
