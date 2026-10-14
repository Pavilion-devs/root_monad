/** Read-only testnet preflight and unsigned deployment artifact. Never signs or sends. */
import {writeFileSync,mkdirSync,readFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {getAddress,keccak256} from 'ethers';
import {compile} from '../src/chain.js';

const args=process.argv.slice(2);
const options:Record<string,string>={};
for(let i=0;i<args.length;i+=2){
 if(!['--rpc-url','--output','--deployer'].includes(args[i]) || !args[i+1] || options[args[i]])throw Error('Usage: prepare-monad.ts [--rpc-url HTTPS_URL] [--output FILE] [--deployer PUBLIC_ADDRESS]');
 options[args[i]]=args[i+1];
}
const rpcUrl=options['--rpc-url']??'https://testnet-rpc.monad.xyz';
const url=new URL(rpcUrl);
if(url.protocol!=='https:' || url.username || url.password || url.hash)throw Error('HTTPS_RPC_REQUIRED');
async function rpc(method:string,params:any[]){
 const response=await fetch(rpcUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method,params}),signal:AbortSignal.timeout(15000)});
 if(!response.ok)throw Error('RPC_UNAVAILABLE');
 const body=await response.json();if(body.error || !('result' in body))throw Error('RPC_UNAVAILABLE');return body.result;
}
try{
 const chainId=BigInt(await rpc('eth_chainId',[]));
 if(chainId!==10143n)throw Error('WRONG_CHAIN');
 const block=await rpc('eth_getBlockByNumber',['finalized',false]);
 const age=Date.now()/1000-Number(BigInt(block?.timestamp??'0x0'));
 if(!block?.hash || !block?.number || age>120 || age < -30)throw Error('FINALIZED_STATE_UNAVAILABLE');
 const built=compile();const bytecode='0x'+built.evm.bytecode.object;
 const transaction:any={chainId:'0x279f',value:'0x0',data:bytecode};
 let account:any=null;
 if(options['--deployer']){
  const address=getAddress(options['--deployer']);
  transaction.from=address;
  transaction.nonce=await rpc('eth_getTransactionCount',[address,'pending']);
  transaction.gasPrice=await rpc('eth_gasPrice',[]);
  const estimate=BigInt(await rpc('eth_estimateGas',[{from:address,data:bytecode,value:'0x0'}]));
  transaction.gas='0x'+((estimate*120n+99n)/100n).toString(16);
  const balance=BigInt(await rpc('eth_getBalance',[address,'latest']));
  const maximumFee=BigInt(transaction.gas)*BigInt(transaction.gasPrice);
  account={address,balanceWei:balance.toString(),estimatedGas:estimate.toString(),maximumFeeAtObservedGasPriceWei:maximumFee.toString(),sufficientAtObservedGasPrice:balance>=maximumFee};
 }
 const observed={number:block.number,hash:block.hash,timestamp:block.timestamp};
 const artifact={formatVersion:1,preparedAt:new Date().toISOString(),network:'monad_testnet',chainId:10143,
  readOnly:true,broadcast:false,rpcOrigin:url.origin,finalizedBlock:observed,account,
  compiler:'solc 0.8.36',evmVersion:'cancun',optimizer:{enabled:true,runs:200},
  sourceSha256:createHash('sha256').update(readFileSync('contracts/MemoryRegistry.sol')).digest('hex'),
  creationBytecodeKeccak256:keccak256(bytecode),abi:built.abi,unsignedTransaction:transaction,
  remaining:['Supply a dedicated funded testnet deployer if account is null','Recheck nonce, fee budget and balance immediately before signing','Sign and persist transaction bytes/hash before broadcasting','Verify successful canonical receipt below the finalized tip and deployed code','Pin the resulting contract address in owner, service and client configuration','Run live conflict, revocation and migration checks; record actual costs and latency'],
  trust:'Pinned trusted RPC; no consensus or light-client verification'};
 const destination=resolve(options['--output']??'results/monad-deployment-preparation.json');
 mkdirSync(dirname(destination),{recursive:true});writeFileSync(destination,JSON.stringify(artifact,null,2)+'\n',{mode:0o600});
 console.log(JSON.stringify({artifact:destination,chainId:10143,finalizedBlock:observed,broadcast:false,deployerProvided:Boolean(account)}));
}catch{
 // Endpoint URLs may contain provider credentials. Do not print transport exceptions.
 console.error('Monad preparation failed. Check the HTTPS endpoint, chain ID, finalized state, and optional deployer balance. No transaction was signed or sent.');
 process.exitCode=1;
}
