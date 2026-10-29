const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const Rules=vm.runInNewContext(fs.readFileSync('assets/studio/client/web/workflow-core.js','utf8')+'\nWorkflowRules;');
const review={pairs:[{a:0,b:1}],items:[{index:0},{index:1},{index:2}]};
assert.equal(Rules.visible({status:'adopted'},{status:'adopted',similarity:''},review,0),true);
assert.equal(Rules.visible({status:'review'},{status:'adopted'},review,0),false);
assert.equal(Rules.visible(null,{similarity:'similar'},review,1),true);
assert.equal(Rules.visible(null,{similarity:'different'},review,2),true);
assert.equal(Rules.visible(null,{similarity:'different'},review,3),false); // Untested text cannot be called different.
assert.equal(Rules.visible(null,{similarity:'similar'},null,0),false);
const source='说明文字\n脚本1\n甲\n\n脚本2\n乙';const parts=Rules.split(source,'numbered');
assert.equal(parts.length,2);assert.equal(parts.join(''),source);assert.equal(Rules.split('1.卖点\n2.卖点','numbered').length,1);
assert.equal(Rules.split('开场\n---\n另一个开场','separator').length,2);assert.equal(Rules.split(source,'one')[0],source);
console.log('Workflow: status filtering, reviewed-only similarity filtering and lossless script boundaries passed.');
