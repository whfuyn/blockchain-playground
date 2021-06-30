FROM python:3
WORKDIR /btc
COPY bin/bitcoind /usr/bin
COPY bin/bitcoin-cli /usr/bin
RUN chmod +x /usr/bin/bitcoind
RUN chmod +x /usr/bin/bitcoin-cli
COPY btc.py .
CMD ["python", "btc.py" ]
