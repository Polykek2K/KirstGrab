# KirstGrab

KirstGrab — графический загрузчик видео и аудио на базе `yt-dlp`. Проект поддерживает Windows x86_64 и macOS Apple Silicon (`arm64`).

## macOS

Готовый релиз содержит отдельный архив для Apple Silicon:

- `KirstGrab-<version>-macos-arm64.zip` — Mac с Apple Silicon.

Распакуйте подходящий архив и перенесите `KirstGrab.app` в `/Applications`. Сборки создаются на macOS 15, поэтому заявленная минимальная версия системы — macOS 15.

Приложение включает `yt-dlp`, FFmpeg, FFprobe и Deno и не зависит от Homebrew на компьютере пользователя. Cookies хранятся в `~/Library/Application Support/KirstGrab/cookies.txt`, а не внутри подписанного `.app`.

Автообновление выбирает архив строго по ОС и архитектуре, требует и проверяет SHA-256 digest из GitHub Release API, меняет весь `.app` с резервной копией и проверяет bundle identifier, версию и подпись перед перезапуском. Для Developer ID builds также требуется та же Apple Team ID, что у установленного приложения. Если каталог приложения недоступен для записи, откроется страница релиза для ручного обновления.

### Локальная сборка на Mac

Требования:

- Python 3.13 с Tkinter;
- Homebrew;
- FFmpeg (`brew install ffmpeg`; скрипт установит его при необходимости).

```bash
bash ./build-local-macos.sh --version 1.6.1
```

Результаты:

- `dist/KirstGrab.app`;
- `KirstGrab-1.5.2-macos-<architecture>.zip`.

Для повторной сборки с уже загруженными `yt-dlp` и Deno используйте `--skip-download`. Версия аргумента обязана совпадать с `CURRENT_VERSION`. Проверка сборки запускает все вложенные утилиты, сканирует каждый Mach-O и symlink внутри bundle, проверяет архитектуру, переносимость `otool`, `Info.plist` и code signature. В приложение добавляется `BUILD-MANIFEST.txt` с точными версиями и конфигурацией FFmpeg.

Без `KIRSTGRAB_CODESIGN_IDENTITY` создаётся ad-hoc signed development build. Для публичного распространения задайте Developer ID Application identity, подпишите приложение и выполните notarization — workflow поддерживает это через secrets, перечисленные ниже.

## GitHub Actions release

Сборки разделены на reusable workflows `Build Windows` и `Build macOS`; каждый из них можно запустить отдельно для получения платформенного Actions artifact. Единственный источник версии — `CURRENT_VERSION` в `KirstGrab.py`.

Общий workflow `Build and Release` читает эту версию один раз и передаёт одинаковое значение выбранным сборкам. Параметр `target` принимает `windows`, `macos` или `all`, поэтому можно собрать и выпустить одну платформу либо обе сразу. По умолчанию workflow работает в безопасном режиме build-only и не создаёт тег или Release.

Для официального релиза запустите workflow с `publish_release: true` именно из ветки `main`. Windows-only релиз не требует Apple secrets. Для `macos` и `all` отсутствие любого секрета подписи, ошибка Developer ID signing или notarization прерывает сборку; неподписанный macOS-архив не публикуется.

Платформенные архивы можно добавлять по очереди в один релиз: существующий тег принимается только когда он указывает на тот же commit, после чего новый архив добавляется в GitHub Release. Повторная публикация одноимённого архива заменяет его.

Для production-подписи macOS настройте:

- `MACOS_CERTIFICATE_BASE64` — Developer ID certificate в формате PKCS#12, закодированный base64;
- `MACOS_CERTIFICATE_PASSWORD`;
- `MACOS_CODESIGN_IDENTITY`;
- `MACOS_NOTARY_APPLE_ID`;
- `MACOS_NOTARY_PASSWORD` — app-specific password;
- `MACOS_NOTARY_TEAM_ID`.

Секреты передаются только шагам проверки конфигурации, импорта сертификата, подписи и notarization. Скачивание зависимостей, сборка и все исполняющие код smoke-тесты завершаются до импорта Developer ID certificate; после импорта CI только переподписывает уже проверенный `.app` системным `codesign`.

## Проверки

Кроссплатформенные unit-тесты не требуют запуска GUI:

```bash
python -m unittest discover -s tests -v
python -m py_compile KirstGrab.py kirstgrab_platform.py
```

## Лицензия

Код KirstGrab распространяется по GNU GPLv3. Сведения о вложенных инструментах находятся в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
