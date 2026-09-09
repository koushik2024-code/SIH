'use strict';
const pendingConnection = new URLSearchParams(location.search).get('connect');
const $ = id => document.getElementById(id);
const labels = {executive_summary:'Executive summary',linkedin:'LinkedIn post',x_post:'X / Twitter',email:'Email',advisory:'Advisory',infographic:'Infographic specification',presentation:'Presentation outline',video:'Video'};
let languages = [{name:'English',code:'en',voice_ready:false}], setup = {}, historyItems = [], historySelected = new Set(), connectionList = [], editing = null, draft = null, publishing = null, publishDraft = null, connecting = null;
let token = '', sourceList = [], selected = new Set(), currentRoute = null, previewSequence = 0, busy = false;
const videoURLs = new Map();
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const p = value => `<p>${escapeHTML(value)}</p>`;
const list = values => `<ul>${values.map(v => `<li>${escapeHTML(v)}</li>`).join('')}</ul>`;
function notify(message, error = false) { $('notice').classList.remove('hidden'); $('notice').textContent = message; $('notice').classList.toggle('error', error); }
function errorText(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(errorText).join('\n');
  if (!detail) return 'The request could not be completed.';
  if (detail.errors) return detail.errors.map(e => (e.output_type ? (labels[e.output_type] || e.output_type) + ': ' : '') + errorText(e.detail || e)).join('\n');
  if (detail.verification?.errors) return errorText(detail.verification.errors);
  return detail.message || detail.msg || 'Processing failed. Check local setup and try again.';
}
async function refreshSetup() {
  setup = await api('/api/setup'); languages = setup.languages;
  for (const id of ['language','revisionLanguage']) {
    const previous = $(id).value;
    $(id).innerHTML = languages.map(l => `<option>${escapeHTML(l.name)}</option>`).join('');
    if (languages.some(l => l.name === previous)) $(id).value = previous;
  }
  $('setupStatus').textContent = 'Local model & media setup';
  $('setupDetails').replaceChildren();
  for (const text of [setup.ocr.message, ...setup.video_output.messages, setup.video_input.message,
    `Revision model: ${setup.revision_model}`, `Online images: ${setup.web_images_enabled ? 'enabled' : 'disabled by operator'}`,
    `Publishing: ${setup.publishing_enabled ? 'enabled' : 'disabled by operator'}`, 'Text translation quality depends on the local model. Narration requires a language-matched Piper voice.']) {
    const node = document.createElement('p'); node.textContent = text; $('setupDetails').append(node);
  }
  $('revisionModelHint').textContent = `Runs locally with ${setup.revision_model}.`;
  updateVideoControls();
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', 'Bearer ' + token);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const requestToken = token;
  const response = await fetch(path, {...options, headers});
  if (requestToken && requestToken !== token) throw new Error('Session changed. Sign in again.');
  if (!response.ok) {
    let detail; try { detail = (await response.json()).detail; } catch { detail = 'Request failed'; }
    if (response.status === 401) signOut();
    throw new Error(errorText(detail));
  }
  return options.blob ? response.blob() : response.json();
}
function signOut() {
  token = ''; selected.clear(); sourceList = []; currentRoute = null;
  for (const url of videoURLs.values()) URL.revokeObjectURL(url);
  videoURLs.clear(); $('appPage').classList.add('hidden'); $('loginPage').classList.remove('hidden');
  $('password').value = ''; $('results').replaceChildren(); $('historyDetail').replaceChildren();
  previewSequence++; editing = draft = publishing = publishDraft = null; historyItems = []; historySelected.clear();
  document.querySelectorAll('dialog[open]').forEach(d => d.close());
  for (const id of ['sourcesList','historyList','sourcePicker','connectionCards','publicationList','editorFields','editorPreview','publishPreview']) $(id).replaceChildren();
  for (const id of ['pasted','url','instruction','query','revisionInstruction','recipients']) $(id).value = '';
  $('connectionForm').reset();

}
async function action(button, fn) {
  button.disabled = true;
  try { await fn(); } catch (error) { notify(error.message, true); }
  finally { button.disabled = false; }
}
$('loginForm').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try {
    const result = await api('/api/auth/login', {method:'POST', body:JSON.stringify({username:$('username').value,password:$('password').value})});
    token = result.access_token; $('accountName').textContent = $('username').value; $('avatar').textContent = $('username').value.slice(0,1).toUpperCase(); $('password').value = ''; $('loginMsg').textContent = '';
    $('loginPage').classList.add('hidden'); $('appPage').classList.remove('hidden');
    await refreshSources(); await updateHistoryCount(); await showPage('generate'); await refreshSetup(); await openPendingConnection(); notify('Signed in. Add or select source material to begin.');
  } catch (error) { $('loginMsg').textContent = error.message; }
  finally { button.disabled = false; }
});
$('logout').addEventListener('click', signOut);
async function showPage(page) {
  ['generate','sources','history','connections'].forEach(name => $(name+'Page').classList.toggle('hidden', name !== page));
  document.querySelectorAll('[data-page]').forEach(button => button.classList.toggle('active',button.dataset.page === page));
  $('pageTitle').textContent = {generate:'Create',sources:'Sources',history:'History',connections:'Connections'}[page];
  if (page === 'sources') await loadSources();
  if (page === 'history') await loadHistory();
  if (page === 'connections') { await loadConnections(); await refreshSetup(); await loadPublications(); }
}
document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => action(button, () => showPage(button.dataset.page))));
const formatIcons = {executive_summary:'file',linkedin:'linkedin',x_post:'x',email:'mail',advisory:'shield',infographic:'chart',presentation:'layers',video:'video'};
const compactLabels = {executive_summary:'Summary',linkedin:'LinkedIn',x_post:'X / Thread',email:'Email',advisory:'Advisory',infographic:'Infographic',presentation:'Presentation',video:'Video'};
$('outputChoices').innerHTML = Object.entries(labels).map(([key,label]) => `<label class="output-choice" title="${escapeHTML(label)}"><input type="checkbox" value="${key}" ${key === 'linkedin' ? 'checked' : ''}><span data-icon="${formatIcons[key]}"></span><span>${compactLabels[key]}</span></label>`).join('');
function drawPicker() {
  $('selectionCount').textContent = `${selected.size} selected`;
  $('sourcePicker').innerHTML = sourceList.map(s => `<label class="source-option"><input type="checkbox" data-source="${s.id}" ${selected.has(s.id)?'checked':''}><span><strong>${escapeHTML(s.name)}</strong><small>#${s.id} · ${escapeHTML(s.metadata.parser || 'text')} · Ready</small></span></label>`).join('') || '<p class="muted">Add a source to begin.</p>';
}
async function refreshSources() { sourceList = await api('/api/sources'); selected = new Set([...selected].filter(id=>sourceList.some(s=>s.id===id))); $('sourceTotal').textContent = sourceList.length; drawPicker(); }
$('sourcePicker').addEventListener('change', async event => {
  const id = Number(event.target.dataset.source); if (!id) return;
  event.target.checked ? selected.add(id) : selected.delete(id); drawPicker(); await previewRoute();
});
function routeBody() { return {source_ids:[...selected],retrieval_requested:$('retrieve').checked,persistent_knowledge:$('persistent').checked}; }
async function previewRoute() {
  const sequence = ++previewSequence; currentRoute = null; $('generate').disabled = true;
  if (!selected.size) { $('routeName').textContent = 'Awaiting sources'; $('routeReason').textContent = 'Select sources to preview the route.'; $('queryArea').classList.add('hidden'); return; }
  try {
    const result = await api('/api/route', {method:'POST',body:JSON.stringify(routeBody())});
    if (sequence !== previewSequence) return;
    currentRoute = result; $('routeName').textContent = result.route; $('routeReason').textContent = result.route_reason;
    $('tokenEstimate').textContent = `About ${result.estimated_tokens.toLocaleString()} input tokens · heuristic estimate`;
    $('queryArea').classList.toggle('hidden', result.route !== 'RAG');
    if (result.route === 'RAG' && !$('query').value && !['inform',''].includes($('objective').value.trim())) $('query').value = $('objective').value;
    $('generate').disabled = busy;
  } catch (error) { if (sequence === previewSequence) notify(error.message, true); }
}
['retrieve','persistent'].forEach(id => $(id).addEventListener('change', previewRoute));
async function added(result) {
  selected.add(result.source_id); await refreshSources(); await previewRoute();
  notify(`Source #${result.source_id} ready · ${result.metadata.parser} · ${result.evidence_count} evidence chunks.`);
}
$('upload').addEventListener('click', () => action($('upload'), async () => {
  const files = [...$('files').files]; if (!files.length) throw new Error('Choose a file first.');
  for (const file of files) {
    notify('Reading ' + file.name + '...'); const form = new FormData(); form.append('file', file);
    await added(await api('/api/sources/upload',{method:'POST',body:form}));
  }
  $('files').value = ''; $('fileSummary').textContent = 'No files selected';
}));
$('addText').addEventListener('click', () => action($('addText'), async () => {
  await added(await api('/api/sources/text',{method:'POST',body:JSON.stringify({name:$('sourceName').value,text:$('pasted').value})}));
}));
$('addUrl').addEventListener('click', () => action($('addUrl'), async () => {
  await added(await api('/api/sources/url',{method:'POST',body:JSON.stringify({url:$('url').value})}));
}));
function contentHTML(type, d) {
  switch(type) {
    case 'linkedin': return `<h3>${escapeHTML(d.hook)}</h3>` + d.body.map(p).join('') + p(d.takeaway) + p(d.hashtags.join(' '));
    case 'email': return `<section class="email-preview"><div class="email-subject"><small>SUBJECT</small><h3>${escapeHTML(d.subject)}</h3></div><div class="email-body">` + p(d.greeting) + d.body.map(p).join('') + (d.call_to_action ? p(d.call_to_action) : '') + `<div class="email-signoff">${p(d.sign_off)}</div></div></section>`;
    case 'executive_summary': return `<h3>${escapeHTML(d.title)}</h3>` + p(d.summary) + list(d.key_points);
    case 'x_post': return d.posts.map((post,i) => `<div class="slide"><small>Post ${i+1} · ${[...post].length}/280 characters</small>${p(post)}</div>`).join('');
    case 'advisory': return `<h3>${escapeHTML(d.title)}</h3>` + (d.severity?p('Severity: '+d.severity):'') + p(d.summary) + p('Affected: '+d.affected.join(', ')) + d.sections.map(p).join('') + list(d.recommendations);
    case 'infographic': return `<h3>${escapeHTML(d.title)}</h3>` + p(d.headline) + list(d.key_points) + p('Visual elements: '+d.visual_elements.join(', ')) + p('Layout: '+d.layout);
    case 'presentation': return d.slides.map((s,i) => `<section class="slide"><small>SLIDE ${i+1}</small><h3>${escapeHTML(s.title)}</h3>${list(s.bullets)}${p(s.speaker_notes)}</section>`).join('');
    case 'video': return `<h3>${escapeHTML(d.title)}</h3>` + d.scenes.map(s => `<details><summary>Scene ${s.scene}: ${escapeHTML(s.caption)}</summary>${p(s.narration)}</details>`).join('');
    default: return p('Unsupported saved output format');
  }
}
async function showOutput(output, container) {
  const item = document.createElement('article'); item.className = 'output'; item.dataset.assetId = output.asset_id;
  const publishable = ['linkedin','x_post','email'].includes(output.output_type) && output.controls?.content_scope !== 'internal';
  item.innerHTML = `<div class="output-header"><div class="output-heading"><span class="format-avatar">${icon(formatIcons[output.output_type])}</span><div><h3>${escapeHTML(labels[output.output_type])}</h3><small>${escapeHTML(output.controls?.language || 'English')} · Version ${output.version || 1} · ${escapeHTML(output.edit_mode || 'Generated')}</small></div></div><div class="actions"><button class="secondary" data-action="copy">Copy</button><button class="secondary" data-action="download">${icon('download')} Download</button><button class="secondary" data-action="edit">${icon('edit')} Edit</button></div></div><div class="output-content">${contentHTML(output.output_type,output.result)}</div><div class="citation-links"></div><div class="output-footer"><small>Structure & citation IDs checked.<br>Review factual support before sharing.</small><div class="actions"><button class="secondary" data-action="revise">${icon('spark')} Ask AI to revise</button>${publishable ? '<button data-action="publish">Review & submit ↗</button>' : '<span class="pill subtle">'+(output.controls?.content_scope === 'internal'?'INTERNAL':'DOWNLOAD & SHARE')+'</span>'}</div></div>`;
  const citations = item.querySelector('.citation-links');
  for (const [id,url] of Object.entries(output.citation_links || {})) {
    const link = document.createElement('a'); link.textContent = id; link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; citations.append(link);
  }
  item.querySelector('[data-action="copy"]').addEventListener('click', event => action(event.currentTarget, async () => { await navigator.clipboard.writeText(output.rendered_text); notify('Content copied.'); }));
  item.querySelector('[data-action="download"]').addEventListener('click', event => action(event.currentTarget, () => download(output.asset_id,output.output_type)));
  item.querySelector('[data-action="edit"]').addEventListener('click', () => openEditor(output, false));
  item.querySelector('[data-action="revise"]').addEventListener('click', () => openEditor(output, true));
  item.querySelector('[data-action="publish"]')?.addEventListener('click', () => openPublish(output));
  item.querySelector('.output-content').dir=['Arabic','Urdu'].includes(output.controls?.language)?'rtl':'auto';
  container.append(item);
  if (output.output_type === 'video') {
    const frames = document.createElement('button'); frames.textContent = 'Download scene frames'; frames.className = 'secondary';
    frames.addEventListener('click', event => action(event.currentTarget, async () => {
      const blob = await api(`/api/assets/${output.asset_id}/frames`, {blob:true});
      const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `asset_${output.asset_id}_frames.zip`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    })); item.querySelector('.actions').append(frames);

    const play = document.createElement('button'); play.textContent = 'Load video preview'; play.className = 'secondary';
    item.querySelector('.output-content').prepend(play);
    play.addEventListener('click', () => action(play, async () => {
      const blob = await api(`/api/assets/${output.asset_id}/download`,{blob:true});
      const key = output.asset_id; if (videoURLs.has(key)) URL.revokeObjectURL(videoURLs.get(key));
      const url = URL.createObjectURL(blob); videoURLs.set(key,url);
      const video = document.createElement('video'); video.controls = true; video.src = url; video.setAttribute('aria-label',output.result.title); play.replaceWith(video);
    }));
    const credits = document.createElement('details'); credits.className = 'media-credits';
    const summary = document.createElement('summary'); summary.textContent = 'Image sources & credits'; credits.append(summary);
    for (const scene of output.media?.scenes || []) {
      const media = scene.media || {}; const line = document.createElement('p');
      line.textContent = `Scene ${scene.scene}: ${media.provider || media} ${media.creator ? ' · '+media.creator+' · '+media.license : ''}`;
      if (safeExternal(media.source_url)) { const a = document.createElement('a'); a.href=media.source_url; a.target='_blank'; a.rel='noopener noreferrer'; a.textContent=' View original'; line.append(a); }
      credits.append(line);
    }
    for (const warning of output.media?.image_warnings || []) { const node=document.createElement('p');node.textContent=warning;credits.append(node); }
    item.querySelector('.output-content').append(credits);
  }
}
async function download(id,type) {
  const blob = await api(`/api/assets/${id}/download`,{blob:true}); const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = `asset_${id}.${type === 'video'?'mp4':'md'}`; link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
}
$('generate').addEventListener('click', async () => {
  const output_types = [...document.querySelectorAll('#outputChoices input:checked')].map(e=>e.value);
  if (!currentRoute || !selected.size || !output_types.length) { notify('Select sources and at least one output.',true); return; }
  busy = true; $('generate').disabled = true; $('results').innerHTML = '<div class="loading-card" role="status"><span class="spinner"></span><h3>Bringing your content together…</h3><p>Local generation, translation and media can take a few minutes.</p><small>Your outputs will appear here when ready.</small></div>';
  try {
    const body = {...routeBody(),output_types,content_scope:$('internalMode').checked?'internal':'public',image_mode:$('imageMode').value,audience:$('audience').value,tone:$('tone').value,language:$('language').value,detail_level:$('detail').value,objective:$('objective').value,style:$('style').value,user_instruction:$('instruction').value,retrieval_query:currentRoute.route === 'RAG' ? $('query').value : null};
    const result = await api('/api/transform',{method:'POST',body:JSON.stringify(body)});
    $('results').replaceChildren(); for (const output of result.outputs) await showOutput(output,$('results'));
    for (const error of result.errors || []) { const node = document.createElement('p'); node.className = 'error-box'; node.textContent = `${labels[error.output_type]}: ${errorText(error.detail)}`; $('results').append(node); }
    notify(`${result.outputs.length} output(s) saved to history.`); await updateHistoryCount();
  } catch (error) { $('results').textContent = error.message; notify('Generation failed. Check the details below.',true); }
  finally { busy = false; $('generate').disabled = !currentRoute; }
});
const iconPaths = {
 spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',folder:'M3 7V5h6l2 2h10v13H3Z',clock:'M12 8v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',link:'m10 13 4-4 M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0 M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0',shield:'M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z m-4 9 3 3 5-6',logout:'M10 4H4v16h6 M10 12h11 m-4-4 4 4-4 4',sun:'M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M12 2v2 M12 20v2 M2 12h2 M20 12h2 M5 5l1 1 M18 18l1 1 M5 19l1-1 M18 6l1-1',upload:'M12 16V3 m-4 4 4-4 4 4 M4 15v6h16v-6',plus:'M12 5v14 M5 12h14',arrow:'M4 12h16 m-5-5 5 5-5 5',file:'M14 3H5v18h14V8Z M14 3v5h5 M8 12h8 M8 16h6',linkedin:'M5 9v11 M5 5v.1 M10 20V9h4v2c4-4 6 0 6 3v6 M10 9v11',x:'M4 3h4l12 18h-4Z M20 3 4 21',mail:'M3 5h18v14H3Z m0 1 9 7 9-7',chart:'M4 20V4 M4 20h17 M9 16v-5 M14 16V7 M19 16V4',layers:'m12 3 10 5-10 5L2 8Z M2 12l10 5 10-5 M2 16l10 5 10-5',video:'M3 5h12v14H3Z m12 6 6-4v10l-6-4',download:'M12 3v12 m-4-4 4 4 4-4 M4 16v5h16v-5',edit:'m15 4 5 5-11 11H4v-5Z m-2 2 5 5',trash:'M3 6h18 M9 6V3h6v3 M6 6l1 15h10l1-15 M10 10v7 M14 10v7'};
function icon(name) { return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${iconPaths[name] || iconPaths.file}"></path></svg>`; }
function hydrateIcons(root=document) { root.querySelectorAll('[data-icon]').forEach(n=>{n.innerHTML=icon(n.dataset.icon);}); }
hydrateIcons();
function safeExternal(url) { try {const u=new URL(url);return u.protocol==='https:'&&!u.username&&!u.password;}catch{return false;} }
$('themeToggle').addEventListener('click',()=>{document.body.classList.toggle('dark');$('themeToggle').setAttribute('aria-pressed',document.body.classList.contains('dark'));});
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>$(b.dataset.close).close()));
document.querySelectorAll('[data-input]').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('[data-input]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-selected',b===button);});
  ['file','text','url'].forEach(id=>$(id+'Input').classList.toggle('hidden',id!==button.dataset.input));
}));
$('files').addEventListener('change',()=>$('fileSummary').textContent=[...$('files').files].map(f=>f.name).join(', ')||'No files selected');
for (const e of ['dragenter','dragover']) $('dropZone').addEventListener(e,event=>{event.preventDefault();$('dropZone').classList.add('dragging');});
for (const e of ['dragleave','drop']) $('dropZone').addEventListener(e,event=>{event.preventDefault();$('dropZone').classList.remove('dragging');});
$('dropZone').addEventListener('drop',event=>{if(event.dataTransfer.files.length){$('files').files=event.dataTransfer.files;$('files').dispatchEvent(new Event('change'));}});
function updateVideoControls() {
  const video=!!document.querySelector('#outputChoices input[value="video"]:checked');
  $('videoControls').classList.toggle('hidden',!video);
  const current=languages.find(l=>l.name===$('language').value);
  $('languageHint').textContent=video ? (current?.voice_ready ? 'Matching local narration voice found. Review pronunciation in the preview.' : `Text translation is available. ${$('language').value} video needs a matching installed Piper voice.`) : 'A separate local translation pass preserves structure and citation IDs.';
  $('imageMode').disabled=$('internalMode').checked||setup.web_images_enabled===false;
}
$('language').addEventListener('change',updateVideoControls);$('outputChoices').addEventListener('change',updateVideoControls);$('internalMode').addEventListener('change',updateVideoControls);
async function updateHistoryCount(){historyItems=await api('/api/assets');$('historyTotal').textContent=historyItems.length;}
async function loadSources(){
  await refreshSources();$('sourcesList').replaceChildren();
  for(const source of sourceList){
    const record=document.createElement('article');record.className='record';
    record.innerHTML=`<div class="record-top"><span class="format-avatar">${icon('file')}</span><span class="badge subtle">SOURCE #${source.id}</span></div><h3>${escapeHTML(source.name)}</h3><p>${escapeHTML(source.media_type)}</p><p>${escapeHTML(source.created_at)} UTC</p><details><summary>Parser & provenance</summary><pre>${escapeHTML(JSON.stringify(source.metadata,null,2))}</pre><p>SHA-256: ${escapeHTML(source.content_hash)}</p></details><div class="actions"><button class="secondary" data-view>View text</button><button class="secondary danger" data-delete>Delete</button></div><div class="source-text hidden"></div>`;
    record.querySelector('[data-view]').addEventListener('click',event=>action(event.currentTarget,async()=>{const detail=await api('/api/sources/'+source.id);const node=record.querySelector('.source-text');node.classList.remove('hidden');node.textContent=detail.content;}));
    record.querySelector('[data-delete]').addEventListener('click',()=>confirmDelete('Delete this source?', 'Its stored text and retrieval index will be removed. Sources used by saved outputs must be kept until those outputs are deleted.', async()=>{await api('/api/sources/'+source.id,{method:'DELETE'});selected.delete(source.id);await loadSources();await previewRoute();notify('Source deleted.');}));
    $('sourcesList').append(record);
  }
  if(!sourceList.length)$('sourcesList').innerHTML='<div class="empty">No sources yet. Add material in Create.</div>';
}
async function loadHistory(){await updateHistoryCount();historySelected=new Set([...historySelected].filter(id=>historyItems.some(a=>a.id===id)));drawHistory();}
function visibleHistory(){const q=$('historySearch').value.toLowerCase();return historyItems.filter(a=>(!$('historyFilter').value||a.output_type===$('historyFilter').value)&&[a.title,...a.source_names,a.language].join(' ').toLowerCase().includes(q));}
function drawHistory(){
  $('historyList').replaceChildren();const rows=visibleHistory();
  for(const asset of rows){
    const record=document.createElement('article');record.className='record';
    record.innerHTML=`<div class="record-top"><span class="format-avatar">${icon(formatIcons[asset.output_type])}</span><label class="check"><input type="checkbox" aria-label="Select output ${asset.id}" data-select ${historySelected.has(asset.id)?'checked':''}></label></div><span class="eyebrow">${escapeHTML(compactLabels[asset.output_type])} · ${escapeHTML(asset.language)}</span><h3 class="line-clamp">${escapeHTML(asset.title)}</h3><p>${escapeHTML(asset.source_names.join(', '))}</p><p>Version ${asset.version} · ${escapeHTML(asset.edit_mode)}${asset.parent_asset_id?' · from #'+asset.parent_asset_id:''}</p><p>${escapeHTML(asset.created_at)} UTC</p><div class="actions"><button class="secondary" data-open>Open & edit</button><button class="icon-button" data-download aria-label="Download output">${icon('download')}</button><button class="icon-button danger secondary" data-delete aria-label="Delete output">${icon('trash')}</button></div>`;
    record.querySelector('[data-select]').addEventListener('change',e=>{e.target.checked?historySelected.add(asset.id):historySelected.delete(asset.id);updateSelection();});
    record.querySelector('[data-open]').addEventListener('click',e=>action(e.currentTarget,async()=>{const output=await api('/api/assets/'+asset.id);$('historyDetail').replaceChildren();await showOutput(output,$('historyDetail'));$('historyDetail').scrollIntoView({behavior:'smooth',block:'start'});}));
    record.querySelector('[data-download]').addEventListener('click',e=>action(e.currentTarget,()=>download(asset.id,asset.output_type)));
    record.querySelector('[data-delete]').addEventListener('click',()=>requestDeleteOutputs([asset.id]));$('historyList').append(record);
  }
  if(!rows.length)$('historyList').innerHTML='<div class="empty">No matching outputs. Create something new or adjust your search.</div>';
  updateSelection();
}
function updateSelection(){const rows=visibleHistory();$('selectAllHistory').checked=!!rows.length&&rows.every(a=>historySelected.has(a.id));$('deleteSelected').disabled=!historySelected.size;$('deleteSelected').textContent=historySelected.size?`Delete selected (${historySelected.size})`:'Delete selected';}
$('historyFilter').innerHTML += Object.entries(labels).map(([k,v])=>`<option value="${k}">${escapeHTML(v)}</option>`).join('');
$('historySearch').addEventListener('input',drawHistory);$('historyFilter').addEventListener('change',drawHistory);
$('selectAllHistory').addEventListener('change',e=>{for(const a of visibleHistory())e.target.checked?historySelected.add(a.id):historySelected.delete(a.id);drawHistory();});
$('deleteSelected').addEventListener('click',()=>requestDeleteOutputs([...historySelected]));
let pendingDelete=null;
function confirmDelete(title,text,fn){$('confirmTitle').textContent=title;$('confirmText').textContent=text;pendingDelete=fn;$('confirmDialog').showModal();}
$('confirmDelete').addEventListener('click',e=>action(e.currentTarget,async()=>{const fn=pendingDelete;$('confirmDialog').close();await fn();}));
function requestDeleteOutputs(ids){confirmDelete(`Delete ${ids.length} output${ids.length===1?'':'s'}?`,'This removes the selected saved versions and their files. Published social posts and sent emails remain at their destinations.',async()=>{
  const result=await api('/api/assets/delete-selection',{method:'POST',body:JSON.stringify({ids})});
  for(const id of ids){historySelected.delete(id);document.querySelectorAll(`[data-asset-id="${id}"]`).forEach(n=>n.remove());if(videoURLs.has(id)){URL.revokeObjectURL(videoURLs.get(id));videoURLs.delete(id);}}
  await loadHistory();notify(result.message+(result.file_cleanup_pending?' Some files could not be removed from disk; see audit log.':''));
});}
function editorMode(ai){$('manualPane').classList.toggle('hidden',ai);$('aiPane').classList.toggle('hidden',!ai);$('manualTab').classList.toggle('active',!ai);$('aiTab').classList.toggle('active',ai);}
$('manualTab').addEventListener('click',()=>editorMode(false));$('aiTab').addEventListener('click',()=>editorMode(true));
function openEditor(output,ai){editing=output;draft=structuredClone(output.result);$('editorTitle').textContent=labels[output.output_type]+` · Version ${output.version||1}`;$('editorError').textContent='';$('revisionInstruction').value='';$('revisionLanguage').value=output.controls?.language||'English';editorMode(ai);drawEditor();$('editorDialog').showModal();}
function updateEditorPreview(){try{$('editorPreview').innerHTML=contentHTML(editing.output_type,draft);}catch{$('editorPreview').textContent='Complete all fields to preview this output.';}}
function drawEditor(){
  $('editorFields').replaceChildren();
  function walk(value,parent,key,label){
    const wrap=document.createElement('div');
    if(key==='citations'||key==='scene') {wrap.className='editor-citations';wrap.textContent=label+': '+(Array.isArray(value)?value.join(', '):value);return wrap;}
    if(typeof value==='string'||value===null){
      wrap.className='editor-field';const lab=document.createElement('label');lab.textContent=label.replaceAll('_',' ');
      const input=document.createElement('textarea');input.value=value??'';input.rows=(value?.length||0)>130?4:2;input.dir='auto';lab.append(input);wrap.append(lab);
      input.addEventListener('input',()=>{parent[key]=input.value|| (key==='severity'?null:'');updateEditorPreview();});
    } else if(Array.isArray(value)){
      wrap.className='editor-group';const h=document.createElement('h3');h.textContent=label.replaceAll('_',' ');wrap.append(h);
      value.forEach((v,i)=>{const row=document.createElement('div');row.className='array-item';row.append(walk(v,value,i,`${label.replaceAll('_',' ')} ${i+1}`));
        // Object groups retain their schema topology; all string list items can be added/removed.
        if(typeof v==='string'){const remove=document.createElement('button');remove.className='remove-field secondary danger';remove.textContent='Remove';remove.addEventListener('click',()=>{value.splice(i,1);drawEditor();});row.append(remove);}wrap.append(row);});
      if(!value.length||typeof value[0]==='string'){const add=document.createElement('button');add.className='add-field secondary';add.textContent='+ Add item';add.addEventListener('click',()=>{value.push('');drawEditor();});wrap.append(add);}
    } else if(value&&typeof value==='object'){
      wrap.className='editor-group';if(label){const h=document.createElement('h3');h.textContent=label;wrap.append(h);}
      for(const [k,v] of Object.entries(value))wrap.append(walk(v,value,k,k));
    }
    return wrap;
  }
  for(const [k,v] of Object.entries(draft))$('editorFields').append(walk(v,draft,k,k));updateEditorPreview();
}
async function saveEditor(ai){
  const original=editing; if(!original)return;
  $('saveEdit').disabled=$('runRevision').disabled=true;$('editorError').textContent=ai?'Creating a local revision…':'Saving your edit…';
  try{
    const body=ai?{instruction:$('revisionInstruction').value,language:$('revisionLanguage').value}:{result:draft};
    const result=await api(`/api/assets/${original.asset_id}/${ai?'revise':'edit'}`,{method:'POST',body:JSON.stringify(body)});
    $('editorDialog').close();const container=$('historyPage').classList.contains('hidden')?$('results'):$('historyDetail');
    await showOutput(result,container);container.lastElementChild.scrollIntoView({behavior:'smooth',block:'center'});await updateHistoryCount();if(!$('historyPage').classList.contains('hidden'))drawHistory();notify(`Version ${result.version} saved. The original is still in history.`);
  }catch(error){$('editorError').textContent=error.message;}
  finally{$('saveEdit').disabled=$('runRevision').disabled=false;}
}
$('saveEdit').addEventListener('click',()=>saveEditor(false));$('runRevision').addEventListener('click',()=>saveEditor(true));
function openPublish(output){publishing=output;publishDraft=null;$('recipients').value='';$('recipientArea').classList.toggle('hidden',output.output_type!=='email');$('publishPreview').replaceChildren();$('publishError').textContent='';$('submitPublish').disabled=true;$('loadPublishPreview').disabled=false;$('submitPublish').textContent='Submit';$('publishDialog').showModal();if(output.output_type!=='email')preparePublish();}
function recipients(){return $('recipients').value.split(',').map(s=>s.trim()).filter(Boolean);}
$('recipients').addEventListener('input',()=>{publishDraft=null;$('submitPublish').disabled=true;$('publishPreview').replaceChildren();});
async function preparePublish(){
  $('loadPublishPreview').disabled=true;$('publishError').textContent='';
  try{
    const addrs=publishing.output_type==='email'?recipients():[];
    publishDraft=await api(`/api/publishing/${publishing.asset_id}/preview`,{method:'POST',body:JSON.stringify({recipients:addrs})});publishDraft.recipients=addrs;
    const p=publishDraft.payload;
    const text=publishDraft.channel==='email'?`From: ${p.from}\nTo: ${p.to.join(', ')}\nSubject: ${p.subject}\n\n${p.body}`:publishDraft.channel==='x'?p.posts.map((t,i)=>`Post ${i+1}\n${t}`).join('\n\n———\n\n'):p.text;
    $('publishPreview').innerHTML=`<div class="destination"><span class="badge">${escapeHTML(publishDraft.channel.toUpperCase())}</span><strong>${escapeHTML(publishDraft.account)}</strong></div>${p.author?'<p class="small muted">Author: '+escapeHTML(p.author)+' · Public visibility</p>':''}<pre class="publish-payload">${escapeHTML(text)}</pre><p class="small muted">${escapeHTML(publishDraft.message)}</p>`;
    $('submitPublish').disabled=false;$('submitPublish').textContent=publishDraft.channel==='email'?'Submit · Send email':`Submit · Post to ${publishDraft.channel==='x'?'X':'LinkedIn'}`;
  }catch(error){$('publishError').textContent=error.message;}
  finally{$('loadPublishPreview').disabled=false;}
}
$('loadPublishPreview').addEventListener('click',preparePublish);
$('submitPublish').addEventListener('click',async()=>{
  if(!publishDraft)return;const version=publishDraft;$('submitPublish').disabled=true;$('loadPublishPreview').disabled=true;$('publishError').textContent='Submitting…';
  try{const result=await api(`/api/publishing/${publishing.asset_id}/submit`,{method:'POST',body:JSON.stringify({recipients:version.recipients,preview_token:version.preview_token})});
    const message=result.status==='submitted'?'Submission accepted.':`Submission status: ${result.status}. Check Connections → Submission activity before trying again.`;
    $('publishError').textContent=message+(result.duplicate_prevented?' Duplicate submission prevented.':'');notify(message,result.status!=='submitted');
    $('submitPublish').textContent=result.status==='submitted'?'Submitted':'Check submission activity';publishDraft=null;
  }catch(error){$('publishError').textContent=error.message+' Check submission activity before preparing another preview.';}
  finally{$('loadPublishPreview').disabled=false;}
});
async function openPendingConnection(){
  if (!['linkedin','x'].includes(pendingConnection)) return;
  history.replaceState(null, '', '/');
  await showPage('connections');
  openConnection(pendingConnection, connectionList.find(c=>c.channel===pendingConnection));
}
async function loadConnections(){
  connectionList=await api('/api/publishing/connections');$('connectionCards').replaceChildren();
  for(const channel of ['linkedin','x','email']){
    const saved=connectionList.find(c=>c.channel===channel);const title={linkedin:'LinkedIn',x:'X / Twitter',email:'Email'}[channel];const record=document.createElement('article');record.className='connection-card';
    record.innerHTML=`<span class="format-avatar">${icon(channel==='email'?'mail':channel)}</span><h3>${title}</h3><p>${{linkedin:'Publish a reviewed text post to your authorized profile or organization.',x:'Publish a post or a connected thread using your authorized X account.',email:'Send a formatted email through your own secure SMTP connection.'}[channel]}</p><span class="connection-status">${saved?'Configured · '+escapeHTML(saved.label):'Not connected'}</span><small>${saved?'Credentials saved; provider permissions are checked on submit.':'Your provider’s posting permissions are required.'}</small><div class="actions"><button class="secondary" data-connect>${saved?'Update connection':'Connect account'}</button>${saved?'<button class="icon-button danger secondary" data-disconnect aria-label="Disconnect account">'+icon('logout')+'</button>':''}</div>`;
    record.querySelector('[data-connect]').textContent = channel === 'email' ? (saved ? 'Reconnect with Google' : 'Connect with Google') : (saved ? 'Update credentials' : 'Enter credentials');
    record.querySelector('[data-connect]').addEventListener('click', event => action(event.currentTarget, async () => {
      if (channel !== 'email') return openConnection(channel,saved);
      const result = await api('/api/auth/oauth/connect/google', {method:'POST'});
      location.href = result.url;
    }));
    if (channel === 'email') {
      const manual = document.createElement('button'); manual.className='secondary'; manual.textContent='Other email provider'; manual.addEventListener('click',()=>openConnection(channel,saved)); record.querySelector('.actions').append(manual);
    }
    record.querySelector('[data-disconnect]')?.addEventListener('click',()=>confirmDelete('Disconnect this account?','The encrypted credentials for this account will be removed.',async()=>{await api('/api/publishing/connections/'+channel,{method:'DELETE'});await loadConnections();notify('Account disconnected.');}));
    $('connectionCards').append(record);
  }
}
function openConnection(channel,saved){connecting=channel;$('connectionForm').reset();$('connectionLabel').value=saved?.label||'';$('connectionError').textContent='';$('connectionTitle').textContent='Connect '+{linkedin:'LinkedIn',x:'X',email:'email'}[channel];$('socialFields').classList.toggle('hidden',channel==='email');$('linkedinFields').classList.toggle('hidden',channel!=='linkedin');$('emailFields').classList.toggle('hidden',channel!=='email');
  $('connectionHelp').textContent={linkedin:'Use an OAuth user access token with w_member_social (or authorized organization posting access), plus your author URN. See docs/STUDIO_SETUP.md for setup.',x:'Use an OAuth user-context access token with tweet.write and required read/user scopes. An app-only bearer token cannot publish on your behalf. See docs/STUDIO_SETUP.md.',email:`Use your provider’s SMTP app password. Allowed servers: ${(setup.smtp_allowed_hosts||[]).join(', ')}. The sender must be authorized by that account.`}[channel];$('connectionDialog').showModal();}
$('connectionForm').addEventListener('submit',async e=>{
  e.preventDefault();const button=e.submitter;button.disabled=true;$('connectionError').textContent='';
  try{const body={label:$('connectionLabel').value,...(connecting==='email'?{smtp_host:$('smtpHost').value,smtp_port:Number($('smtpPort').value),smtp_username:$('smtpUsername').value,smtp_password:$('smtpPassword').value,from_email:$('fromEmail').value}:{access_token:$('accessToken').value,author_urn:connecting==='linkedin'?$('authorUrn').value:''})};await api('/api/publishing/connections/'+connecting,{method:'PUT',body:JSON.stringify(body)});$('connectionForm').reset();$('connectionDialog').close();await loadConnections();notify('Connection saved. No content has been sent.');}
  catch(error){$('connectionError').textContent=error.message;}finally{button.disabled=false;}
});
$('connectionDialog').addEventListener('close',()=>{$('accessToken').value='';$('smtpPassword').value='';});
async function loadPublications(){
  const rows=await api('/api/publishing/history');$('publicationList').replaceChildren();
  for(const row of rows){const node=document.createElement('article');node.className='activity-row';node.innerHTML=`<strong>${escapeHTML(row.channel.toUpperCase())} · Output #${row.asset_id}</strong> <span class="badge">${escapeHTML(row.status)}</span><small>${escapeHTML(row.created_at)} UTC · Submission #${row.id}</small>`;
    for(const url of row.result.urls||[])if(safeExternal(url)){const a=document.createElement('a');a.href=url;a.textContent='View published post ↗';a.target='_blank';a.rel='noopener noreferrer';node.append(a);}
    const summary=document.createElement('p');summary.textContent=row.result.message||row.result.note||'';node.append(summary);
    if(row.result.accepted){const p=document.createElement('p');p.textContent='Accepted: '+row.result.accepted.join(', ')+(row.result.refused?.length?' · Refused: '+row.result.refused.join(', '):'');node.append(p);}
    $('publicationList').append(node);
  }
  if(!rows.length)$('publicationList').innerHTML='<div class="empty">No submissions yet. Review a saved output to submit it.</div>';
}
$('refreshPublications').addEventListener('click',e=>action(e.currentTarget,loadPublications));

async function initSocialLogin() {
  const query = new URLSearchParams(location.search);
  if (query.has('signin')) history.replaceState(null, '', '/');
  try {
    const providers = await api('/api/auth/oauth/providers');
    for (const provider of providers) {
      const button = document.querySelector(`[data-oauth="${provider.provider}"]`);
      button.disabled = !provider.enabled;
      button.title = provider.enabled ? 'Sign in securely' : 'Operator setup required: docs/OAUTH_VIDEO_SETUP.md';
      button.addEventListener('click', () => { location.href = `/api/auth/oauth/${provider.provider}/start`; });
    }
    if (providers.some(p => !p.enabled)) $('oauthHelp').textContent = 'Unavailable providers need operator configuration. See docs/OAUTH_VIDEO_SETUP.md.';
    if (query.get('signin') === 'failed') throw new Error('Sign-in was cancelled or failed. Please try again.');
    if (query.get('signin') === 'complete') {
      const result = await api('/api/auth/oauth/session', {method:'POST'});
      token = result.access_token;
      $('accountName').textContent = result.username;
      $('avatar').textContent = result.username.slice(0,1).toUpperCase();
      $('loginPage').classList.add('hidden'); $('appPage').classList.remove('hidden');
      await refreshSources(); await updateHistoryCount(); await showPage('generate'); await refreshSetup(); await openPendingConnection();
    }
  } catch (error) { $('loginMsg').textContent = error.message; }
}
initSocialLogin();
