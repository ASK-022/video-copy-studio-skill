import {writeFileSync,renameSync,mkdirSync} from 'node:fs';
import {resolve,join} from 'node:path';
/** The updater accepts only a per-launch nonce written after both workbenches are healthy. */
export function acknowledgeDesktopBoot({dataDir,version,pid=process.pid,director,editor},env=process.env){
  const nonce=env.CONTENT_HUB_UPDATE_NONCE,path=env.CONTENT_HUB_UPDATE_ACK;
  if(!path||!nonce||!director||!editor)return false;
  if(!/^[0-9a-f]{48}$/.test(nonce)||resolve(path)!==resolve(dataDir,'updates',`boot-${nonce}.json`))throw Error('Invalid update health receipt path');
  mkdirSync(join(dataDir,'updates'),{recursive:true});
  writeFileSync(path+'.tmp',JSON.stringify({nonce,version,pid,director:true,editor:true}));renameSync(path+'.tmp',path);return true;
}
