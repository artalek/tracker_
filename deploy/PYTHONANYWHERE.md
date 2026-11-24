# Развёртывание на PythonAnywhere

В инструкции используется бесплатный тариф, Python 3.13 и SQLite. Если в **Web** доступен Python 3.12, выберите 3.12 и запустите скрипт с `PYTHON_BIN=python3.12`. Версии в настройках веб-приложения и виртуального окружения должны совпадать. [Версии Python](https://help.pythonanywhere.com/pages/PythonVersions/)

## Первый запуск

1. В панели **Web** выберите **Add a new web app → Manual configuration → Python 3.13**. Запомните выданный домен, например `username.pythonanywhere.com` или `username.eu.pythonanywhere.com`.
2. В **Consoles → Bash** выполните команды, подставив ваш домен.

   ```bash
   cd ~
   git clone https://github.com/artalek/tracker_.git
   cd tracker_
   bash deploy/pythonanywhere.sh username.pythonanywhere.com
   ```

   Скрипт установит зависимости, создаст закрытый файл `.env` со случайным секретом, применит миграции и соберёт статику. При повторном запуске он использует уже созданные настройки и базу. Подготовьте контакт для обращений и задайте `PRIVACY_OPERATOR_NAME` и `PRIVACY_CONTACT_EMAIL` в `.env` через редактор **Files**.

3. В разделе **Code** установите **Source code** и **Working directory** в `/home/username/tracker_`. В поле **Virtualenv** укажите `/home/username/tracker_/.venv`.
4. Откройте ссылку **WSGI configuration file** и замените содержимое шаблоном из [pythonanywhere_wsgi.py](pythonanywhere_wsgi.py). Для клона в `~/tracker_` путь в шаблоне менять не нужно.
5. В **Static files** добавьте URL `/static/` и каталог `/home/username/tracker_/staticfiles`. Включите **Force HTTPS** и нажмите **Reload**. Откройте сайт по HTTPS, выполните конвертацию и проверьте график.

Для доступа к Django Admin создай администратора отдельной командой. Пароль вводится в консоли PythonAnywhere и хранится в базе в виде хеша.

```bash
.venv/bin/python manage.py createsuperuser
```

Если страница сообщает об ошибке, откройте **Web → Error log**. При проверке Django могут появиться предупреждения про распространение HSTS на поддомены и браузерный preload. Для выделенного поддомена учебного проекта эти настройки не включены.

## Следующие обновления

```bash
cd ~/tracker_
git pull --ff-only origin main
bash deploy/pythonanywhere.sh username.pythonanywhere.com
```

Затем нажмите **Web → Reload**. Храните резервную копию SQLite отдельно от репозитория. Актуальные курсы подгружаются по запросу. Для ручного обновления выполните `.venv/bin/python manage.py update_rates`.

[Развёртывание Django на PythonAnywhere](https://help.pythonanywhere.com/pages/DeployExistingDjangoProject/) · [Настройка статических файлов](https://help.pythonanywhere.com/pages/DjangoStaticFiles/) · [HTTPS](https://help.pythonanywhere.com/pages/ForcingHTTPS/)
