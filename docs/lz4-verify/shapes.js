// Classifies every non-last sequence in 4KB pages by where its match source sits and which optional fields it uses.
const fs=require('fs');const L=require('./lz4core.js');
function run(name,buf){const c={seq:0,own:0,earlier:0,span:0,overlap:0,lit0:0,litExt:0,matExt:0,pages:0,lastOnly:0,restoredOverlap:0,restoredAll:0};
 for(let i=0;i+4096<=buf.length&&c.pages<4000;i+=4096){const r=L.compress(buf.subarray(i,i+4096),false);c.pages++;if(r.seqs.length===1)c.lastOnly++;
  for(const s of r.seqs){if(s.last)continue;c.seq++;
   const over=s.matchLen>s.offset;if(over)c.overlap++;
   if(s.litLen===0)c.lit0++;
   if(s.litPos-s.tokPos-1>0)c.litExt++;if(s.end-s.mlPos>0)c.matExt++;
   // Source start relative to this sequence's own literals.
   if(s.litLen>0&&s.matchSrc>=s.litSrc)c.own++;else if(s.matchSrc+Math.min(s.matchLen,s.offset)<=s.litSrc)c.earlier++;else c.span++;
  }}
 const p=x=>(c.seq?x/c.seq*100:0).toFixed(1)+'%';
 console.log(name.padEnd(20),'pages',c.pages,'seqs',c.seq,'| source: own literal',p(c.own),'earlier seqs',p(c.earlier),'spans',p(c.span),'| overlap',p(c.overlap),'| lit0',p(c.lit0),'litExt',p(c.litExt),'matExt',p(c.matExt),'| pages all-literal',c.lastOnly);}
const s=L.samples(4096);for(const k of ['text','pointers'])run('synthetic '+k,Buffer.from(s[k]));
for(const [n,f] of [['dict words','/usr/share/dict/words'],['/bin/zsh','/bin/zsh'],['/bin/ls','/bin/ls']])run(n,fs.readFileSync(f));
const z=L.compress(new Uint8Array(4096));console.log('zero hex',Buffer.from(z.out).toString('hex'));
