/* Playable standard-tuning voicings. Every displayed note belongs to the chord. */
"use strict";
const GuitarVoicings = (() => {
  const pcs = {C:0,"C#":1,Db:1,D:2,"D#":3,Eb:3,E:4,Fb:4,"E#":5,F:5,"F#":6,Gb:6,G:7,"G#":8,Ab:8,A:9,"A#":10,Bb:10,B:11,Cb:11,"B#":0};
  const intervals = {"": [0,4,7], m:[0,3,7], "7":[0,4,7,10], maj7:[0,4,7,11], m7:[0,3,7,10], "6":[0,4,7,9], m6:[0,3,7,9], mMaj7:[0,3,7,11], dim:[0,3,6], aug:[0,4,8], dim7:[0,3,6,9], m7b5:[0,3,6,10], sus2:[0,2,7], sus4:[0,5,7]};
  const tuning=[40,45,50,55,59,64], cache=new Map();
  const roots=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
  let dictionary=null,aliases={},requirements={},catalogue=new Map(),preferences=new Map();
  const open={C:[-1,3,2,0,1,0],D:[-1,-1,0,2,3,2],E:[0,2,2,1,0,0],F:[1,3,3,2,1,1],G:[3,2,0,0,0,3],A:[-1,0,2,2,2,0],B:[-1,2,4,4,4,2],Am:[-1,0,2,2,1,0],Em:[0,2,2,0,0,0],Dm:[-1,-1,0,2,3,1],C7:[-1,3,2,3,1,0],D7:[-1,-1,0,2,1,2],E7:[0,2,0,1,0,0],A7:[-1,0,2,0,2,0],G7:[3,2,0,0,0,1],Am7:[-1,0,2,0,1,0],Em7:[0,2,0,0,0,0],Dm7:[-1,-1,0,2,1,1],Cmaj7:[-1,3,2,0,0,0],Dmaj7:[-1,-1,0,2,2,2],Fmaj7:[-1,-1,3,2,1,0],Amaj7:[-1,0,2,1,2,0],Emaj7:[0,2,1,1,0,0]};
  function parse(label){
    const m=/^([A-G](?:#|b)?)(.*?)(?:\/([A-G](?:#|b)?))?$/.exec(label);
    if(!m)return null;
    const quality=aliases[m[2]]??m[2];
    if(!(quality in intervals))return null;
    const root=pcs[m[1]],bass=pcs[m[3]||m[1]];
    const notes=intervals[quality].map(n=>(root+n)%12);
    const required=(requirements[quality]||intervals[quality]).map(n=>(root+n)%12);
    if(!notes.includes(bass))notes.push(bass);
    return {root,bass,notes,required,quality,label:roots[root]+quality+(bass!==root?'/'+roots[bass]:'')};
  }
  function valid(shape,chord){
    const sounded=shape.flatMap((f,i)=>f<0?[]:[tuning[i]+f]);
    const required=chord.required||chord.notes;
    return sounded.length>=Math.min(3,required.length) && Math.min(...sounded)%12===chord.bass &&
      sounded.every(n=>chord.notes.includes(n%12)) && required.every(n=>sounded.some(v=>v%12===n));
  }
  function find(label){
    if(cache.has(label)) return cache.get(label);
    const chord=parse(label);
    if(!chord){cache.set(label,null);return null;}
    const chosen=preferences.get(chord.label);
    if(chosen&&valid(chosen,chord)){cache.set(label,chosen);return chosen;}
    if(open[chord.label] && valid(open[chord.label],chord)){cache.set(label,open[chord.label]);return open[chord.label];}
    // Prefer familiar movable E/Am shapes to sparse, theoretically valid grips.
    // In particular Bm is x24432, with the index barre from A through high E.
    const families={
      "":[[0,2,2,1,0,0],[-1,0,2,2,2,0]],
      m:[[0,2,2,0,0,0],[-1,0,2,2,1,0]],
      "7":[[0,2,0,1,0,0],[-1,0,2,0,2,0]],
      m7:[[0,2,0,0,0,0],[-1,0,2,0,1,0]],
      maj7:[[0,2,1,1,0,0],[-1,0,2,1,2,0]],
      mMaj7:[[0,2,1,0,0,0],[-1,0,2,1,1,0]],
      "6":[[0,2,2,1,2,0],[-1,0,2,2,2,2]],
      m6:[[0,2,2,0,2,0],[-1,0,2,2,1,2]]
    };
    if(chord.bass===chord.root && families[chord.quality]){
      const candidates=families[chord.quality].map((shape,i)=>{
        const offset=(chord.root-(i===0?4:9)+12)%12;
        return shape.map(f=>f<0?f:f+offset);
      }).filter(shape=>valid(shape,chord));
      candidates.sort((a,b)=>Math.max(...a)-Math.max(...b));
      if(candidates.length){cache.set(label,candidates[0]);return candidates[0];}
    }
    const known=catalogue.get(chord.label)?.positions.find(p=>valid(p.frets,chord));
    if(known){cache.set(label,known.frets);return known.frets;}
    let best=null,bestScore=Infinity;
    for(let start=1;start<=10;start++){
      const options=tuning.map(note=>[-1,0,...Array.from({length:4},(_,i)=>start+i)].filter((f,i,a)=>a.indexOf(f)===i && (f<0 || chord.notes.includes((note+f)%12))));
      const shape=[];
      function search(string){
        if(string===6){
          if(!valid(shape,chord)) return;
          const fretted=shape.filter(f=>f>0), sounded=shape.filter(f=>f>=0).length;
          const lo=fretted.length?Math.min(...fretted):0,hi=fretted.length?Math.max(...fretted):0;
          const distinct=new Set(fretted).size;
          // At most four stopped-fret groups; repeated low fret may be a barre.
          if(distinct>4 || hi-lo>3) return;
          let fingers=fretted.length;
          for(const fret of new Set(fretted)){
            const positions=shape.map((f,i)=>f===fret?i:-1).filter(i=>i>=0);
            if(positions.length>1 && shape.slice(positions[0],positions.at(-1)+1).every(f=>f<0||f>=fret))
              fingers=Math.min(fingers,fretted.length-positions.length+1);
          }
          if(fingers>4) return;
          let holes=0,started=false;
          for(const f of shape){if(f>=0)started=true;else if(started)holes++;}
          const score=lo*.7+(hi-lo)*1.4+fretted.length*.2+holes*1.7-sounded*.8-shape.filter(f=>f===0).length*.4;
          if(score<bestScore){bestScore=score;best=shape.slice();}
          return;
        }
        for(const fret of options[string]){shape.push(fret);search(string+1);shape.pop();}
      }
      search(0);
    }
    cache.set(label,best);
    return best;
  }
  function fingering(shape){
    const stopped=shape.map((f,i)=>({f,i})).filter(n=>n.f>0);
    const frets=[...new Set(stopped.map(n=>n.f))].sort((a,b)=>a-b);
    let barre=null;
    for(const fret of frets){
      if(fret!==frets[0])break;
      const positions=stopped.filter(n=>n.f===fret).map(n=>n.i);
      const from=positions[0],to=positions.at(-1);
      if(positions.length>=2 && (to-from>=3 || positions.length>=3 || fret===1 && from===4) && shape.slice(from,to+1).every(f=>f>=fret)){
        barre={fret,from,to,finger:1};break;
      }
    }
    const fingers=shape.map(()=>0);
    let next=1;
    if(barre){for(const n of stopped)if(n.f===barre.fret)fingers[n.i]=1;next=2;}
    for(const n of stopped.sort((a,b)=>a.f-b.f||a.i-b.i)){
      if(!fingers[n.i])fingers[n.i]=next++;
    }
    // Generic voicings may require a second partial barre. Do not print an
    // impossible fifth finger; these still have their exact pitch positions.
    return {barre,fingers:fingers.map(f=>f<=4?f:0)};
  }
  function install(data){
    dictionary=data;aliases=data.aliases||{};requirements={};
    for(const [quality,definition] of Object.entries(data.theory)){
      intervals[quality]=definition.intervals;requirements[quality]=definition.required;
    }
    catalogue=new Map(data.chords.map(c=>[c.label,c]));cache.clear();
  }
  function positions(label){
    const chord=parse(label);if(!chord)return [];
    const result=(catalogue.get(chord.label)?.positions||[]).filter(p=>valid(p.frets,chord)).slice();
    const primary=find(label);
    if(primary&&!result.some(p=>p.frets.join()===primary.join())){
      const info=fingering(primary);result.unshift({frets:primary,fingers:info.fingers,barres:info.barre?[info.barre]:[]});
    }else if(primary){result.sort((a,b)=>Number(b.frets.join()===primary.join())-Number(a.frets.join()===primary.join()));}
    return result;
  }
  function details(label,shape){
    const chord=parse(label),known=chord&&catalogue.get(chord.label)?.positions.find(p=>p.frets.join()===shape.join());
    if(known)return {fingers:known.fingers,barres:known.barres,barre:known.barres[0]||null};
    const result=fingering(shape);return {...result,barres:result.barre?[result.barre]:[]};
  }
  function prefer(label,shape){
    const chord=parse(label);if(!chord||!valid(shape,chord))return false;
    preferences.set(chord.label,shape);cache.clear();return true;
  }
  return {find,parse,valid,fingering,install,positions,details,prefer,
    entries:()=>dictionary?.chords||[],summary:()=>dictionary?.summary||{chords:0,positions:0,families:14},
    qualities:()=>Object.keys(intervals)};
})();
if(typeof module!=="undefined")module.exports=GuitarVoicings;
if(typeof window!=="undefined")window.GuitarVoicings=GuitarVoicings;
