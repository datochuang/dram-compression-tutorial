// Compression ratio of the same data when split into independent blocks of different sizes.
const fs=require('fs');const L=require('./lz4core.js');
const sizes=[256,1024,4096,16384,32768];
for(const [n,f] of [['dict words','/usr/share/dict/words'],['/bin/zsh','/bin/zsh'],['/bin/ls','/bin/ls']]){
 const b=fs.readFileSync(f).subarray(0,1<<20);const row=[];
 for(const z of sizes){let i=0,o=0,t=0;for(;i+z<=b.length;i+=z){o+=L.compress(b.subarray(i,i+z),false).out.length;t+=z}row.push(z+':'+(o/t*100).toFixed(1)+'%')}
 console.log(n.padEnd(12),(b.length/1024|0)+'KiB',row.join('  '));}
