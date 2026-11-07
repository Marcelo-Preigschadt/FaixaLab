"use strict";
const assert = require('node:assert/strict');
const guitar = require('../faixalab/web/guitar.js');
const roots=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
const theory={'':[0,4,7],m:[0,3,7],'7':[0,4,7,10],maj7:[0,4,7,11],m7:[0,3,7,10],'6':[0,4,7,9],m6:[0,3,7,9],mMaj7:[0,3,7,11],dim:[0,3,6],aug:[0,4,8],dim7:[0,3,6,9],m7b5:[0,3,6,10],sus2:[0,2,7],sus4:[0,5,7]};
const tuning=[40,45,50,55,59,64];let checked=0;
for(let root=0;root<12;root++)for(const [quality,intervals] of Object.entries(theory)){
 const label=roots[root]+quality,shape=guitar.find(label);
 assert(shape,label+' has no diagram');
 const notes=shape.flatMap((f,string)=>f<0?[]:[tuning[string]+f]);
 assert.deepEqual([...new Set(notes.map(n=>n%12))].sort((a,b)=>a-b),intervals.map(n=>(n+root)%12).sort((a,b)=>a-b),label);
 assert.equal(Math.min(...notes)%12,root,label+' uses another bass');
 checked++;
}
for(const [label,bass,notes] of [['C/E',4,[0,4,7]],['D/F#',6,[2,6,9]],['Am/C',0,[9,0,4]],['G/B',11,[7,11,2]],['Bb/D',2,[10,2,5]],['Dm7/C',0,[2,5,9,0]]]){
 const shape=guitar.find(label);assert(shape,label);
 const pitches=shape.flatMap((f,string)=>f<0?[]:[tuning[string]+f]);
 assert.equal(Math.min(...pitches)%12,bass,label);
 assert.deepEqual([...new Set(pitches.map(n=>n%12))].sort((a,b)=>a-b),notes.sort((a,b)=>a-b),label);
 checked++;
}
console.log(checked+' chord diagrams contain the specified chord tones and bass.');
for(const [label,shape] of Object.entries({Bm:[-1,2,4,4,3,2],Cm:[-1,3,5,5,4,3],Fm:[1,3,3,1,1,1],'F#m':[2,4,4,2,2,2]})){
 assert.deepEqual(guitar.find(label),shape,label+' uses conventional movable shape');
}
const bm=guitar.fingering(guitar.find('Bm'));
assert.deepEqual(bm.barre,{fret:2,from:1,to:5,finger:1});
assert.deepEqual(bm.fingers,[0,1,3,4,2,1]);
console.log('Bm/Cm/Fm/F#m conventional positions and Bm index barre verified.');
