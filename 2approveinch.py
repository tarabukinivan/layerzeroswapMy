import sys
import json
import os
import time
import requests
import random
import multiprocessing
import os
import asyncio
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider

w3 = AsyncWeb3(AsyncHTTPProvider("https://rpcapi.fantom.network"))

with open('router_abi.json') as f:
    stargate_abi = json.load(f)
with open('usdc_abi.json') as f:
    usdc_abi = json.load(f)
with open('usdt_abi.json') as f:
    usdt_abi = json.load(f)

class Chain:

    def __init__(self, rpc_url, stargate_address, usdc_address, usdt_address, chain_id, explorer_url):
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self.stargate_address = self.w3.to_checksum_address(stargate_address)
        self.stargate_contract = self.w3.eth.contract(address=self.stargate_address,
                                                      abi=stargate_abi)
        self.usdc_contract = self.w3.eth.contract(address=self.w3.to_checksum_address(usdc_address),
                                                  abi=usdc_abi) if usdc_address else None
        self.usdt_contract = self.w3.eth.contract(address=self.w3.to_checksum_address(usdt_address),
                                                  abi=usdt_abi) if usdt_address else None
        self.chain_id = chain_id
        self.blockExplorerUrl = explorer_url

class Polygon(Chain):
    def __init__(self):
        super().__init__(
            'https://polygon.llamarpc.com',
            '0x45A01E4e04F14f7A4a6702c74187c5F6222033cd',
            '0x2791bca1f2de4661ed88a30c99a7a9449aa84174',
            '0xc2132d05d31c914a87c6611c10748aeb04b58e8f',
            109,
            'https://polygonscan.com'
        )


class Fantom(Chain):
    def __init__(self):
        super().__init__(
            'https://rpc.ftm.tools/',
            '0xAf5191B0De278C7286d6C7CC6ab6BB8A73bA2Cd6',
            '0x04068da6c83afcfa0e13ba15a6696662335d5b75',
            None,
            112,
            'https://ftmscan.com'
        )


class Bsc(Chain):
    def __init__(self):
        super().__init__(
            'https://bsc-dataseed.binance.org',
            '0x4a364f8c717cAAD9A442737Eb7b8A55cc6cf18D8',
            None,
            '0x55d398326f99059fF775485246999027B3197955',
            102,
            'https://bscscan.com'
        )


class Avax(Chain):
    def __init__(self):
        super().__init__(
            'https://avalanche-c-chain.publicnode.com/',
            '0x45A01E4e04F14f7A4a6702c74187c5F6222033cd',
            '0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E',
            '0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7',
            106,
            'https://snowtrace.io'
        )


polygon = Polygon()
fantom = Fantom()
bsc = Bsc()
avax = Avax()

async def swap_usdt(chain_from, chain_to, wallet, AMOUNT_TO_SWAP, MIN_AMOUNT):
    try:
        print("USDT")
        account = chain_from.w3.eth.account.from_key(wallet)
        address = account.address
        nonce = await chain_from.w3.eth.get_transaction_count(address)
        gas_price = await chain_from.w3.eth.gas_price
        fees = await chain_from.stargate_contract.functions.quoteLayerZeroFee(chain_to.chain_id,
                                                                              1,
                                                                              "0x0000000000000000000000000000000000001010",
                                                                              "0x",
                                                                              [0, 0,
                                                                               "0x0000000000000000000000000000000000000001"]
                                                                              ).call()

        fee = fees[0]
        print(f"fee: {fee}")
        allowance = await chain_from.usdt_contract.functions.allowance(address, chain_from.stargate_address).call()
        print(f"allowance: {allowance}")
        if allowance < AMOUNT_TO_SWAP:
            max_amount = chain_from.w3.to_wei(2 ** 64 - 1, 'ether')
            approve_txn = await chain_from.usdt_contract.functions.approve(chain_from.stargate_address,
                                                                           max_amount).build_transaction({
                'from': address,
                'gas': 150000,
                'gasPrice': gas_price,
                'nonce': nonce,
            })
            signed_approve_txn = chain_from.w3.eth.account.sign_transaction(approve_txn, wallet)
            approve_txn_hash = await chain_from.w3.eth.send_raw_transaction(signed_approve_txn.rawTransaction)
            print(
                f"{chain_from.__class__.__name__} | USDT APPROVED {chain_from.blockExplorerUrl}/tx/{approve_txn_hash.hex()}")
            nonce += 1

            await asyncio.sleep(30)

        usdt_balance = await chain_from.usdt_contract.functions.balanceOf(address).call()

        if usdt_balance >= AMOUNT_TO_SWAP:

            chainId = chain_to.chain_id
            source_pool_id = 2
            dest_pool_id = 2
            refund_address = account.address
            amountIn = AMOUNT_TO_SWAP
            amountOutMin = MIN_AMOUNT
            lzTxObj = [0, 0, '0x0000000000000000000000000000000000000001']
            to = account.address
            data = '0x'

            swap_txn = await chain_from.stargate_contract.functions.swap(
                chainId, source_pool_id, dest_pool_id, refund_address, amountIn, amountOutMin, lzTxObj, to, data
            ).build_transaction({
                'from': address,
                'value': fee,
                'gas': 500000,
                'gasPrice': await chain_from.w3.eth.gas_price,
                'nonce': await chain_from.w3.eth.get_transaction_count(address),
            })

            signed_swap_txn = chain_from.w3.eth.account.sign_transaction(swap_txn, wallet)
            swap_txn_hash = await chain_from.w3.eth.send_raw_transaction(signed_swap_txn.rawTransaction)
            return swap_txn_hash

        elif usdt_balance < AMOUNT_TO_SWAP:

            min_amount = usdt_balance - (usdt_balance * 5) // 1000

            chainId = chain_to.chain_id
            source_pool_id = 2
            dest_pool_id = 2
            refund_address = account.address
            amountIn = usdt_balance
            amountOutMin = min_amount
            lzTxObj = [0, 0, '0x0000000000000000000000000000000000000001']
            to = account.address
            data = '0x'

            swap_txn = await chain_from.stargate_contract.functions.swap(
                chainId, source_pool_id, dest_pool_id, refund_address, amountIn, amountOutMin, lzTxObj, to, data
            ).build_transaction({
                'from': address,
                'value': fee,
                'gas': 500000,
                'gasPrice': await chain_from.w3.eth.gas_price,
                'nonce': await chain_from.w3.eth.get_transaction_count(address),
            })

            signed_swap_txn = chain_from.w3.eth.account.sign_transaction(swap_txn, wallet)
            swap_txn_hash = await chain_from.w3.eth.send_raw_transaction(signed_swap_txn.rawTransaction)
            return swap_txn_hash
    except Exception as e:
        print(f"Exception occurred in swap_usdt: {e}")

async def swap_usdc(chain_from: Chain, chain_to: Chain, wallet, AMOUNT_TO_SWAP, MIN_AMOUNT):
    try:
        account = chain_from.w3.eth.account.from_key(wallet)
        address = account.address
        gas_price = await chain_from.w3.eth.gas_price

        fees = await chain_from.stargate_contract.functions.quoteLayerZeroFee(chain_to.chain_id,
                                                                            1,
                                                                            "0x0000000000000000000000000000000000001010",
                                                                            "0x",
                                                                            [0, 0,
                                                                             "0x0000000000000000000000000000000000000001"]
                                                                            ).call()
        fee = fees[0]
        allowance = await chain_from.usdc_contract.functions.allowance(address, chain_from.stargate_address).call()

        #print(f"chain_from->{chain_from}, chain_to->{chain_to}")
        if allowance < AMOUNT_TO_SWAP:
            max_amount = AsyncWeb3.to_wei(2 ** 64 - 1, 'ether')

            approve_txn = await chain_from.usdc_contract.functions.approve(chain_from.stargate_address,
                                                                           max_amount).build_transaction({
                'from': address,
                'gas': 150000,
                'gasPrice': gas_price,
                'nonce': await chain_from.w3.eth.get_transaction_count(address),
            })
            signed_approve_txn = chain_from.w3.eth.account.sign_transaction(approve_txn, wallet)
            approve_txn_hash = await chain_from.w3.eth.send_raw_transaction(signed_approve_txn.rawTransaction)

            print(
                f"{chain_from.__class__.__name__} | USDC APPROVED {chain_from.blockExplorerUrl}/tx/{approve_txn_hash.hex()}")

            await asyncio.sleep(30)

        usdc_balance = await chain_from.usdc_contract.functions.balanceOf(address).call()
        print(f"usdc: {usdc_balance}")
        if usdc_balance >= AMOUNT_TO_SWAP:

            chainId = chain_to.chain_id
            source_pool_id = 1
            dest_pool_id = 1
            refund_address = address
            amountIn = AMOUNT_TO_SWAP
            amountOutMin = MIN_AMOUNT
            lzTxObj = [0, 0, '0x0000000000000000000000000000000000000001']
            to = address
            data = '0x'
            
            print("Баланс есть")
            print (f"chainId: {chainId}, source_pool_id: {source_pool_id}, dest_pool_id: {dest_pool_id}, refund_address: {refund_address}, amountIn: {amountIn}, amountOutMin:{amountOutMin}")
            print (f"lzTxObj: {lzTxObj}, to: {to}, data: {data}")
            
            swap_txn = await chain_from.stargate_contract.functions.swap(
                chainId, source_pool_id, dest_pool_id, refund_address, amountIn, amountOutMin, lzTxObj, to, data
            ).build_transaction({
                'from': address,
                'value': fee,
                'gas': 600000,
                'gasPrice': await chain_from.w3.eth.gas_price,
                'nonce': await chain_from.w3.eth.get_transaction_count(address)
            })

            signed_swap_txn = chain_from.w3.eth.account.sign_transaction(swap_txn, wallet)
            swap_txn_hash = await chain_from.w3.eth.send_raw_transaction(signed_swap_txn.rawTransaction)
            return swap_txn_hash

        elif usdc_balance < AMOUNT_TO_SWAP:

            min_amount = usdc_balance - (usdc_balance * 5) // 1000

            chainId = chain_to.chain_id
            source_pool_id = 1
            dest_pool_id = 1
            refund_address = address
            amountIn = usdc_balance
            amountOutMin = min_amount
            lzTxObj = [0, 0, '0x0000000000000000000000000000000000000001']
            to = address
            data = '0x'
            swap_txn = await chain_from.stargate_contract.functions.swap(
                chainId, source_pool_id, dest_pool_id, refund_address, amountIn, amountOutMin, lzTxObj, to, data
            ).build_transaction({
                'from': address,
                'value': fee,
                'gas': 600000,
                'gasPrice': await chain_from.w3.eth.gas_price,
                'nonce': await chain_from.w3.eth.get_transaction_count(address)
            })

            signed_swap_txn = chain_from.w3.eth.account.sign_transaction(swap_txn, wallet)
            swap_txn_hash = await chain_from.w3.eth.send_raw_transaction(signed_swap_txn.rawTransaction)
            return swap_txn_hash
    except Exception as e:
        print(f"Exception occurred in swap_usdc: {e}")

async def get_claimable_tokens(private_key, w3):
#mim contract
    account = w3.eth.account.from_key(private_key)
    mywallet=account.address
    
    claimable_balance = await w3.eth.get_balance(mywallet)
    claimable_balancehv = AsyncWeb3.from_wei(claimable_balance, 'ether')
    print(f"account: {mywallet} balance: {claimable_balancehv}")
    return mywallet

async def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    private_keys_file = os.path.join(script_dir, 'private_keystmp.txt')

    with open(private_keys_file, 'r') as file:
        private_keys = file.read().splitlines()

    print(f"Total private keys: {len(private_keys)}")
    sys.stdout.flush()

    pool = multiprocessing.Pool(processes=multiprocessing.cpu_count())

    results = []
    for private_key in private_keys:  
        results.append(asyncio.create_task(get_claimable_tokens(private_key, w3)))
        try:
            #1100000000000000 : 0.0011
            from_chain=bsc
            txn_hash = await swap_usdt(from_chain, polygon, private_key, 1100000000000000, 1100000000000000)
            print(
                f"Transaction: {from_chain.blockExplorerUrl}/tx/{txn_hash.hex()}")
        except Exception as e:
            print(e)
#    for result in results:
#        await result

if __name__ == '__main__':
    asyncio.run(main())
