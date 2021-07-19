FROM python:3
WORKDIR /eth
COPY bin/geth /usr/bin
RUN chmod +x /usr/bin/geth
COPY eth.py .
ENTRYPOINT ["python", "eth.py" ]
