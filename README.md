# TrainPlan — автоматизоване формування індивідуальних тренувальних планів

Програмна система до магістерської роботи «Модель автоматизованого формування індивідуальних тренувальних планів».

## Встановлення

```bash
pip install flask scipy numpy          # обов'язково
pip install ortools                    # необов'язково: тоді використовується розв'язувач CP-SAT
pip install pandas matplotlib pytest   # для експериментів і тестів
```

## Запуск вебзастосунку

```bash
python app.py        # http://127.0.0.1:5000
```

## Тести

```bash
python -m pytest -q  # 24 тести
```

## Експерименти (розділ 4)

```bash
python -m experiments.profiles             # 216 синтетичних профілів → results/profiles.json
python -m experiments.run_compare          # модель vs жадібна евристика vs шаблони → results/compare.csv
python -m experiments.llm.make_prompts     # запити до LLM для 18 профілів → llm/prompts/
python -m experiments.llm.evaluate_llm     # оцінювання відповідей LLM з llm/plans/ → results/llm.csv
python -m experiments.run_sensitivity      # чутливість до ваг → results/sensitivity.csv
python tools/import_free_exercise_db.py <free-exercise-db/dist/exercises.json> data/exercises_large.csv
python -m experiments.run_scalability      # масштабованість → results/scalability.csv
python -m experiments.simulate_adaptation  # моделювання адаптації → results/adaptation.csv
python -m experiments.analyze              # статистика і рисунки → results/summary.json, figures/
```

Результати в теці `experiments/results` отримано з розв'язувачем HiGHS (SciPy 1.18) на 2 ядрах.
Якщо встановлено OR-Tools, у `run_compare.py` можна замінити `solver='highs'` на `solver='cpsat'`
і повторити експеримент — числа в розділі 4 потрібно буде оновити.

## Структура

| Тека / файл | Призначення |
|---|---|
| `trainplan/` | модель: дані, обмеження, розв'язувачі, адаптація, метрики, базові методи, БД |
| `app.py`, `web/` | вебзастосунок Flask |
| `data/exercises.csv` | демонстраційна база (72 вправи, ручна розмітка протипоказань) |
| `data/exercises_large.csv` | 558 вправ, імпортованих з free-exercise-db (Unlicense) |
| `tests/` | автоматизовані тести pytest |
| `experiments/` | сценарії експериментів, результати, рисунки |
| `tools/` | імпорт бази вправ, знімки екрана |
