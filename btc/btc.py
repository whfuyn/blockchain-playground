import os
import subprocess
import pathlib
import shutil
import json
import time


def mkdirp(d):
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)


def remove_0x(s):
    return s[2:] if s.startswith('0x') else s


def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(e.stderr)
    return p.stdout.strip()


def spawn_cmd(cmd):
    return subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def build_bitcoin_conf(port, rpc_port, bootnodes):
    conf = [
        'regtest=1',
        '[regtest]',
        'daemon=1',
        f'port={port}',
        f'rpcport={rpc_port}',
    ]
    conf.extend(f'addnode={bootnode}' for bootnode in bootnodes)

    return '\n'.join(conf)


def init_node(datadir, port, rpc_port, bootnodes):
    mkdirp(datadir)
    conf_file = os.path.join(datadir, 'bitcoin.conf')
    with open(conf_file, 'wt') as f:
        f.write(build_bitcoin_conf(port, rpc_port, bootnodes))


def init_net(output_dir, node_cnt):
    print('initializing bitcoin regtest local net..')
    mkdirp(output_dir)

    print('initializing nodes..')
    basic_port = 19555
    basic_rpc_port = 20555
    bootnodes = []
    for i in range(1, node_cnt + 1):
        datadir = os.path.join(output_dir, 'nodes', str(i))
        port = basic_port + 10 * i
        rpc_port = basic_rpc_port + 10 * i

        init_node(datadir, port, rpc_port, bootnodes)

        # Use the first node as bootnode
        if not bootnodes:
            bootnodes.append(f'127.0.0.1:{port}')

    print('bitcoin regtest local net initialized.')


def start_net(net_dir):
    # start node
    nodes_dir = os.path.join(net_dir, 'nodes')
    _, nodes, _ = next(os.walk(nodes_dir))

    for node in nodes:
        datadir = os.path.join(nodes_dir, node)
        start_node(datadir)


def start_node(datadir):
    run_cmd([
        'bitcoind',
        f'-datadir={datadir}',
        '-fallbackfee=0.0001',
        '-daemon'
    ])


def stop_net(net_dir):
    # start node
    nodes_dir = os.path.join(net_dir, 'nodes')
    _, nodes, _ = next(os.walk(nodes_dir))

    for node in nodes:
        datadir = os.path.join(nodes_dir, node)
        stop_node(datadir)


def stop_node(datadir):
    run_cmd([
        'bitcoin-cli',
        f'-datadir={datadir}',
        'stop'
    ])


def clear_net(net_dir):
    if os.path.exists(net_dir):
        stop_net(net_dir)
        shutil.rmtree(net_dir)


def start_miner(datadir, reward_addr=None):
    cli_cmd = ['bitcoin-cli', f'-datadir={datadir}']
    wallet = json.loads(
        run_cmd([*cli_cmd, 'listwallets'])
    )

    if not wallet:
        run_cmd([*cli_cmd, 'createwallet', 'test'])

    if reward_addr is None:
        reward_addr = run_cmd([*cli_cmd, 'getnewaddress', 'reward'])

    while True:
        run_cmd([*cli_cmd, 'generatetoaddress', '1', reward_addr])
        time.sleep(6)


def main():
    output_dir = os.path.join(os.getcwd(), 'tutorial-net')
    if not os.path.exists(output_dir):
        init_net(output_dir, 4)
        start_net(output_dir)

        time.sleep(5)
        print('sleep 5 secs, wait for nodes starting..')

    miner_datadir = os.path.join(output_dir, 'nodes', '1')
    start_miner(miner_datadir)


if __name__ == '__main__':
    main()
