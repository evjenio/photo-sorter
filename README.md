# photo-sorter

Копирует фото и видео из папки с бардаком (`source`) в упорядоченную библиотеку (`dest`).
Source никогда не изменяется.

```
dest/
  2024/
    2024-07/
      12 Georgia - Tbilisi, Stepantsminda/   # день начала события и места
        2024-07-12_14-30-12.heic
        2024-07-12_14-30-12.mov      # Live Photo
    2024-08/
      03 Almaty/
  screenshots/
    2024/07/2024-07-12_15-00-00.png  # скриншоты и записи экрана, вне событий
    _unsorted/
  _unsorted/                         # нет даты ни в EXIF, ни в имени файла
  .photo-sorter/                     # индекс dest и планы
```

## Как работает

1. `scan` читает EXIF (exiftool, офлайн-геокодинг городов), хэширует файлы, склеивает
   Live Photo / RAW+JPEG / `.aae` / `.xmp`, убирает точные дубликаты (внутри source и против dest),
   группирует снимки в события и пишет план `dest/.photo-sorter/plans/<время>/plan.csv`.
   С флагом `--similar` визуально похожие снимки попадают в `similar.csv` для ручного разбора, они всё равно
   копируются. По умолчанию поиск выключен: он декодирует каждое изображение и заметно замедляет scan.
2. Смотришь `plan.csv`, при желании правишь колонку `dest`.
3. `apply` копирует по плану, сверяет хэш копии и обновляет индекс. Повторный запуск безопасен.

Скриншот определяется по имени (`Screenshot_*`, `Снимок экрана *`, …), по EXIF `UserComment=Screenshot`
(iPhone, macOS) или по эвристике: PNG без камеры и GPS с размером, совпадающим с разрешением экрана.
Записи экрана (`RPReplay_*`, `ScreenRecording_*`, `Запись экрана *`) определяются по имени.
Причина видна в колонке `note` плана.

Место определяется офлайн по GPS через базу GeoNames внутри exiftool. Районы крупных городов
(Taganskiy, Presnenskiy) заменяются самим городом, знаки транслитерации (`St’epants’minda`) убираются.

Событие разрывается, если между снимками пауза больше `--gap-hours` (24), сменилась страна
или событие длиннее `--max-event-days` (14). Новые снимки, попавшие во время уже существующего
события в dest, кладутся в его папку.

## Запуск

```sh
docker build --target app -t photo-sorter .

docker run --rm -e TZ=Asia/Almaty --user "$(id -u):$(id -g)" \
  -v /path/to/mess:/source:ro -v /path/to/library:/dest \
  photo-sorter scan /source /dest

docker run --rm -e TZ=Asia/Almaty --user "$(id -u):$(id -g)" \
  -v /path/to/mess:/source:ro -v /path/to/library:/dest \
  photo-sorter apply /source /dest /dest/.photo-sorter/plans/<время>/plan.csv
```

`TZ` нужен для видео: QuickTime хранит время в UTC, и без часового пояса оно сдвинется.

## Тесты

```sh
docker build --target test -t photo-sorter-test . && docker run --rm photo-sorter-test
```
