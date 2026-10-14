import { createInterface } from 'node:readline';
import { rmSync } from 'node:fs';
import { setup,startMemory } from '../tests/memory-support.js';
const s=await setup();
let server=await startMemory({...s.startup,demo:s.demo});
console.log(`Portable memory demo: ${server.url}`);
console.log('Use sample data. Press r + Enter to restart the service; Ctrl+C ends this disposable session.');
const input=createInterface({input:process.stdin});let busy=false,stopping=false;
input.on('line',async line=>{
 if(line.trim()!=='r'||busy)return;busy=true;
 try{const port=Number(new URL(server.url).port);await server.stop();server=await startMemory({...s.startup,genesis:undefined,port,demo:s.demo});console.log(`Service restarted with the same encrypted data: ${server.url}`);}
 catch(e){console.error(e instanceof Error?e.message:e);}finally{busy=false;}
});
async function stop(){if(stopping)return;stopping=true;input.close();await server.stop();rmSync(s.directory,{recursive:true,force:true});process.exit(0);}
process.on('SIGINT',stop);process.on('SIGTERM',stop);
