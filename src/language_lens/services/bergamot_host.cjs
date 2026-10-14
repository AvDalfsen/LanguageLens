// Local-only, line-delimited host for the publisher's Bergamot WASM bindings.
'use strict';
const fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
const {pathToFileURL,fileURLToPath}=require('node:url');
const root=path.resolve(process.argv[2]);
const modelDir=path.resolve(process.argv[3]);
const pair={from:process.argv[4],to:process.argv[5]};
global.require=require;
global.__dirname=root;
global.fetch=async()=>{throw Error('Networking is disabled');};
let listener, reply, translator;
const output=process.stdout.write.bind(process.stdout);
console.log=console.warn=console.error=()=>{};
global.self={
  location:pathToFileURL(path.join(root,'translator-worker.js')),
  fetch:async url=>{
    if(url.protocol!=='file:')throw Error('Only local WASM is allowed');
    const name=fileURLToPath(url);
    if(name!==path.join(root,'bergamot-translator-worker.wasm'))throw Error('Unexpected runtime file');
    return new Response(fs.readFileSync(name),{headers:{'Content-Type':'application/wasm'}});
  },
  importScripts:(...names)=>{
    global.Module=global.self.Module;
    for(const name of names){
      if(name!=='bergamot-translator-worker.js')throw Error('Unexpected script');
      vm.runInThisContext(fs.readFileSync(path.join(root,name),'utf8'),{filename:name});
    }
  },
  addEventListener:(_event,callback)=>{listener=callback;},
  postMessage:value=>reply(value)
};
function buffer(name){const b=fs.readFileSync(path.join(modelDir,name));return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);}
function invoke(name,...args){return new Promise((resolve,reject)=>{
  reply=result=>result.error?reject(Error('Local engine failed')):resolve(result.result);
  listener({data:{id:1,name,args}});
});}
function send(value){output(JSON.stringify(value)+'\n');}
(async()=>{
  vm.runInThisContext(fs.readFileSync(path.join(root,'translator-worker.js'),'utf8'),{filename:'translator-worker.js'});
  await invoke('initialize',{cacheSize:0});
  const names=fs.readdirSync(modelDir);
  const vocab=buffer(names.find(n=>n.endsWith('.spm')));
  await invoke('loadTranslationModel',pair,{
    model:buffer(names.find(n=>n.startsWith('model.')&&n.endsWith('.bin'))),
    shortlist:buffer(names.find(n=>n.startsWith('lex.')&&n.endsWith('.bin'))),vocabs:[vocab,vocab],
    config:{'beam-size':1,'normalize':1.0,'mini-batch':16,'maxi-batch':1000,'maxi-batch-sort':'src','word-penalty':0}
  });
  // Trigger model/JIT preparation before declaring this loaded backend ready.
  await invoke('translate',{models:[pair],texts:[{text:'1',html:false,qualityScores:false}]});
  send({ready:true,model:pair,pid:process.pid});
  const readline=require('node:readline');
  for await(const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})){
    if(Buffer.byteLength(line)>4*1024*1024)break;
    let request;
    try{
      request=JSON.parse(line);
      if(request.command==='quit')break;
      if(request.command==='inspect'){
        send({id:request.id,ok:true,value:{pid:process.pid,model:pair,loaded:true,memory:process.memoryUsage()}});continue;
      }
      if(request.command!=='translate'||typeof request.text!=='string')throw Error('Invalid request');
      const results=await invoke('translate',{models:[pair],texts:[{text:request.text,html:false,qualityScores:false}]});
      send({id:request.id,ok:true,value:results[0].target.text});
    }catch(_error){send({id:request?.id,ok:false,error:'Local translation failed'});}
  }
})().catch(()=>{send({ok:false,error:'Local engine could not load'});process.exitCode=1;});
