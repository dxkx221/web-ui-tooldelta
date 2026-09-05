
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
ENV TZ=Asia/Shanghai
ENV PYTHONPATH=/app
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ENV PIP_EXTRA_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple https://pypi.org/simple"
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONUNBUFFERED=1
ENV TOOLDELTA_DATA_DIR=/app
ENV SHENYI_CREDENTIALS_FILE=/data/.shenyi-panel/credentials.json
ENV SHENYI_ALLOCATOR_URL=""
ENV SHENYI_PANEL_ROOT_DOMAIN=""

WORKDIR /app
VOLUME ["/app/web_panel_data", "/app/插件文件", "/app/插件配置文件", "/app/插件数据文件", "/app/日志文件"]

COPY . /app/
COPY deploy/docker/entrypoint.sh /usr/local/bin/shenyi-entrypoint.sh
RUN chmod +x /usr/local/bin/shenyi-entrypoint.sh

RUN pip3 config set global.index-url "$PIP_INDEX_URL" && \
    pip3 config set global.extra-index-url "$PIP_EXTRA_INDEX_URL"

RUN pip3 install --no-cache-dir -e /app

EXPOSE 5101

ENTRYPOINT ["/usr/local/bin/shenyi-entrypoint.sh"]
CMD ["python", "web_run.py", "--host", "0.0.0.0", "--port", "5101"]
