# Используем Ubuntu 18.04 (GLIBC 2.27) для максимальной совместимости
FROM ubuntu:18.04

# Отключаем вопросы при установке
ENV DEBIAN_FRONTEND=noninteractive

# 1. Устанавливаем инструменты для компиляции (gcc, make и библиотеки, нужные для Python)
RUN apt-get update && apt-get install -y \
    wget build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev \
    libssl-dev libreadline-dev libffi-dev libsqlite3-dev libbz2-dev \
    ca-certificates

# 2. Скачиваем и собираем Python 3.12.0 из исходников
WORKDIR /tmp
RUN wget https://www.python.org/ftp/python/3.12.0/Python-3.12.0.tgz && \
    tar -xf Python-3.12.0.tgz && \
    cd Python-3.12.0 && \
    ./configure --enable-optimizations --enable-shared LDFLAGS="-Wl,-rpath /usr/local/lib" && \
    make -j$(nproc) && \
    make install && \
    ldconfig

# 3. Очищаем мусор (не обязательно, но полезно)
RUN cd /tmp && rm -rf Python-3.12.0*

WORKDIR /app

# 4. Устанавливаем библиотеки через pip3 (он установился вместе с Python)
RUN pip3 install --upgrade pip && \
    pip3 install pandas requests openpyxl xlsxwriter pyinstaller

# Копируем ваш скрипт
COPY report.py .

# Папка для вывода
RUN mkdir /output

# 5. Сборка файла
CMD pyinstaller --clean --onefile --name="Otchet_Yclients_v2" --hidden-import="openpyxl" --hidden-import="xlsxwriter" report.py && \
    cp dist/Otchet_Yclients_v2 /output/