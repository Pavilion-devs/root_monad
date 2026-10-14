/** Independent read-only verifier for the opt-in testnet exercise. Input contains no keys. */
import {readFileSync} from 'node:fs';
import {Contract,JsonRpcProvider} from 'ethers';
import {verifyRegistryContext} from '../src/chain.js';
const input=JSON.parse(readFileSync(0,'utf8'));
const provider=new JsonRpcProvider(input.config.registry.rpcUrl,10143,{staticNetwork:true,cacheTimeout:-1});
try{
 const artifact=JSON.parse(readFileSync('results/monad-deployment-preparation.json','utf8'));
 const registry=new Contract(input.config.domain.verifyingContract,artifact.abi,provider);
 await verifyRegistryContext(input.config,input.bundle,registry,input.historicalDigest);
 console.log(JSON.stringify({verified:true,checkpoint:input.bundle.checkpoint.controlDigest}));
}catch{console.log(JSON.stringify({verified:false}));process.exitCode=1;}
finally{provider.destroy();}
