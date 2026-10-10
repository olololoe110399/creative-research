'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../../src/creative_research/workspaces/assets');
const contexts = new Map();
for (const workspace of ['references', 'lab']) {
  const markup = fs.readFileSync(path.join(root, workspace, 'index.html'), 'utf8');
  const policy = markup.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/)[1];
  assert.match(policy, /script-src 'self';/);
  assert.doesNotMatch(policy.split(';').find(x => x.includes('script-src')), /unsafe-inline|unsafe-eval/);
  assert.match(policy, /connect-src 'self'/);
  assert.match(policy, /object-src 'none'/);
  assert.match(policy, /base-uri 'none'/);

  const context = vm.createContext({
    URL, Intl, console,
    document: { querySelectorAll: () => [] },
    // Startup stays pending; fixtures below exercise real rendering functions without I/O.
    fetch: () => new Promise(() => {}),
    window: {},
  });
  const scripts = Array.from(markup.matchAll(/<script src="([^"]+)"/g), m => m[1]);
  for (const script of scripts) {
    vm.runInContext(fs.readFileSync(path.join(root, workspace, script), 'utf8'), context);
  }
  contexts.set(workspace, context);

  for (const unsafe of [
    'javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'java\tscript:alert(1)',
    'data:text/html,<script>alert(1)</script>', 'file:///tmp/x',
    'http://example.test/x', '//attacker.invalid/x', '\\\\attacker.invalid/x',
    'https://user:password@example.test/x', 'https://', '', null,
  ]) {
    assert.equal(vm.runInContext(`safeExternalUrl(${JSON.stringify(unsafe)})`, context), '');
    assert.equal(vm.runInContext(`safeMediaUrl(${JSON.stringify(unsafe)})`, context), '');
  }
  const https = 'https://www.tiktok.com/@creator/video/123?foo=bar&x=1';
  assert.equal(vm.runInContext(`safeExternalUrl(${JSON.stringify(https)})`, context), https);
  for (const local of ['assets/photo.jpg', './assets/photo.jpg', '/api/media/video/P1']) {
    assert.equal(vm.runInContext(`safeMediaUrl(${JSON.stringify(local)})`, context), local);
    assert.equal(vm.runInContext(`safeExternalUrl(${JSON.stringify(local)})`, context), '');
  }
}

const reference = contexts.get('references');
const unsafe = 'javascript:alert(1)';
const image = 'https://cdn.example.test/image.jpg';
const post = 'https://www.tiktok.com/@creator/video/123';
reference.fixture = {
  reference_id: 'REF-001', item_id: 'POST-001', source: { url: unsafe },
  preview: { thumbnail_url: unsafe }, media: { video_url: unsafe, slide_urls: [unsafe, image] },
};
for (const render of ['detail(fixture)', 'populationDetail(fixture)', 'itemPreview(fixture)', 'media(fixture)']) {
  assert.doesNotMatch(vm.runInContext(render, reference), /(?:href|src)="javascript:/i);
}
assert.match(vm.runInContext('media(fixture)', reference), /https:\/\/cdn.example.test\/image.jpg/);
assert.match(vm.runInContext(`detail({...fixture, source:{url:${JSON.stringify(post)}}})`, reference), /href="https:\/\/www.tiktok.com/);
reference.groupFixture = {
  group_id: 'G1', members: [{ item_id: 'POST-001', url: unsafe, thumbnail_url: unsafe }],
};
assert.doesNotMatch(vm.runInContext('groupDetail(groupFixture)', reference), /(?:href|src)="javascript:/i);

const lab = contexts.get('lab');
lab.fixture = {
  post_uid: 'P1', url: unsafe, preview: { thumbnail_url: unsafe, video_url: unsafe },
};
vm.runInContext(`
  data.postById=new Map([['P1',fixture]]);
  data.familyById=new Map();
  data.production={recipes:[{recipe_id:'REC-001',family_id:'F1',observed_source_posts:[fixture]}]};
  operatingState={outcomes:[{published_url:fixture.url}]};
  drawer=function(title,body){window.lastDrawer=body;};
  openPost('P1');
`, lab);
assert.doesNotMatch(lab.window.lastDrawer, /(?:href|src)="javascript:/i);
assert.doesNotMatch(vm.runInContext("familyThumbs({members:[{post_uid:'P1'}]})", lab), /src="javascript:/i);
vm.runInContext("openProductionRecipe('REC-001')", lab);
assert.doesNotMatch(lab.window.lastDrawer, /href="javascript:/i);
assert.doesNotMatch(vm.runInContext('resultsAndLearningsView()', lab), /href="javascript:/i);
vm.runInContext(`fixture.url=${JSON.stringify(post)}; fixture.preview.thumbnail_url=${JSON.stringify(image)}; openPost('P1');`, lab);
assert.match(lab.window.lastDrawer, /href="https:\/\/www.tiktok.com/);
assert.match(lab.window.lastDrawer, /src="https:\/\/cdn.example.test/);

console.log('Workspace URL allowlists, rendering sinks, and CSP: PASS');
