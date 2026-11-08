const fs=require('fs');const L=require('./lz4core.js');
function page(buf){const r=L.compress(buf,false);let ov=0,non=0,ovN=0,nonN=0;
 for(const s of r.seqs){if(s.last)continue;
  const ext=(s.litPos-s.tokPos-1)+(s.end-s.mlPos);const saved=s.matchLen-3-ext;
  if(s.matchLen>s.offset){ov+=saved;ovN++}else{non+=saved;nonN++}}
 return {out:r.out.length,ov,non,ovN,nonN};}
function run(name,buf){let T={in:0,out:0,ov:0,non:0,ovN:0,nonN:0,pages:0};
 for(let i=0;i+4096<=buf.length&&T.pages<4000;i+=4096){const p=page(buf.subarray(i,i+4096));T.in+=4096;T.out+=p.out;T.ov+=p.ov;T.non+=p.non;T.ovN+=p.ovN;T.nonN+=p.nonN;T.pages++}
 const tot=T.ov+T.non;console.log(name.padEnd(22),'pages',String(T.pages).padStart(5),'out/in',(T.out/T.in*100).toFixed(1).padStart(6)+'%','overlap share of saved',(tot?T.ov/tot*100:0).toFixed(1).padStart(6)+'%','matches ovl/non',T.ovN,T.nonN);}
const s=L.samples(4096);for(const k of Object.keys(s))run('synthetic '+k,Buffer.from(s[k]));
for(const [n,f] of [['dict words','/usr/share/dict/words'],['binary /bin/zsh','/bin/zsh'],['binary /bin/ls','/bin/ls']]){
 try{run(n,fs.readFileSync(f))}catch(e){console.log(n,'unreadable',e.code)}}
const t='go:'+'ab'.repeat(10)+',done!';const r=L.compress(Buffer.from(t));console.log(t,t.length,'->',r.out.length,Buffer.from(r.out).toString('hex'),JSON.stringify(r.seqs.map(q=>[q.litLen,q.offset,q.matchLen])));
const z=L.compress(new Uint8Array(4096));console.log('zero',z.out.length,JSON.stringify(z.seqs.map(q=>[q.litLen,q.offset,q.matchLen])),Buffer.from(z.out).subarray(0,8).toString('hex'));
