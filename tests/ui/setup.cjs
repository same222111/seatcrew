// Exercise the real asynchronous setup renderer without a browser or live accounts.
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = readFileSync(process.argv[2], 'utf8');
(async () => {
  for (const language of ['en', 'zh-CN', 'zh-TW', 'ja', 'es']) {
    const elements = new Map();
    const element = id => {
      if (!elements.has(id)) elements.set(id, {innerHTML:'', value:language, querySelectorAll:()=>[], addEventListener:()=>{}});
      return elements.get(id);
    };
    const detection = {os:{system:'Test',machine:'arm64'}, cpu_count:8, ram_gb:16, disk_free_gb:20, gpu:null,
      keys:{}, recommended:{chat_provider:null, voice:'edge', why_k:['w_demo',''], why:['demo']},
      cli:Object.fromEntries(['codex','claude'].map(k=>[k,{label:k,installed:false,install:'test'}])),
      ollama:{running:false,models:[],install:'https://ollama.com'}, edge_tts:true};
    const context = vm.createContext({L:language, lang:element('lang'), window:{},
      document:{head:{appendChild:()=>{}}, createElement:()=>({}), getElementById:element},
      fetch:async path=>({json:async()=>path==='/api/detect'?detection:{engines:{},clones:[]}}),
      addEventListener:()=>{}, setTimeout:()=>{}});
    vm.runInContext(source, context);
    await context.window.SCSetup.load();
    assert.match(element('sdDetect').innerHTML, /id="sdUse"/);
    assert.match(element('sdVoice').innerHTML, /id="clB"/);
    assert.ok(!element('sdDetect').innerHTML.includes('undefined'));
    context.window.SCSetup.paint();
    console.log('setup renderer OK:', language);
  }
})().catch(error=>{console.error(error);process.exitCode=1});
