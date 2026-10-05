let apps = [], categories = [], selectedCategory = "all", embyTimer = null;
let orderEditMode = false, dragAppId = null;
let backgroundSettings = {enabled:false, url:"", opacity:0.35};
let appearanceSettings = {card_opacity:0.90, card_blur:6, background_blur:2, background_dim:0.55};
let currentTheme = localStorage.getItem("mdkdv-theme") === "light" ? "light" : "dark";


function applyTheme(theme, persist = true){
  currentTheme = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = currentTheme;
  const btn = document.getElementById('themeToggle');
  if(btn){
    btn.textContent = currentTheme === 'dark' ? '☀️ Светлая' : '🌙 Тёмная';
    btn.setAttribute('aria-label', currentTheme === 'dark' ? 'Переключить на светлую тему' : 'Переключить на тёмную тему');
  }
  const select = document.getElementById('themeSelect');
  if(select) select.value = currentTheme;
  if(persist) localStorage.setItem('mdkdv-theme', currentTheme);
}

function toggleTheme(){applyTheme(currentTheme === 'dark' ? 'light' : 'dark');}


function applyAppearance(settings = appearanceSettings, syncControls = false){
  appearanceSettings = {
    card_opacity: Math.max(0.45, Math.min(1, Number(settings?.card_opacity ?? 0.90))),
    card_blur: Math.max(0, Math.min(20, Number(settings?.card_blur ?? 6))),
    background_blur: Math.max(0, Math.min(12, Number(settings?.background_blur ?? 2))),
    background_dim: Math.max(0, Math.min(0.85, Number(settings?.background_dim ?? 0.55)))
  };
  const root=document.documentElement;
  root.style.setProperty('--dashboard-bg-blur', `${appearanceSettings.background_blur}px`);
  root.style.setProperty('--dashboard-bg-dim', appearanceSettings.background_dim);
  root.style.setProperty('--dashboard-card-opacity', appearanceSettings.card_opacity);
  root.style.setProperty('--dashboard-card-blur', `${appearanceSettings.card_blur}px`);

  // Принудительно применяем параметры к уже отрисованным плиткам.
  // Это гарантирует мгновенное обновление без перерисовки Dashboard.
  const cardRgb = getComputedStyle(root).getPropertyValue('--card-rgb').trim() || '25,29,39';
  document.querySelectorAll('.app-card').forEach(card => {
    card.style.setProperty('background-color', `rgba(${cardRgb}, ${appearanceSettings.card_opacity})`);
    card.style.setProperty('backdrop-filter', `blur(${appearanceSettings.card_blur}px)`);
    card.style.setProperty('-webkit-backdrop-filter', `blur(${appearanceSettings.card_blur}px)`);
  });

  if(syncControls) syncAppearanceControls();
}

function applyBackground(settings){
  backgroundSettings = {
    enabled: !!settings?.enabled,
    url: settings?.url || '',
    opacity: 1
  };
  const root=document.documentElement;
  // Прозрачность самого изображения больше не настраивается отдельно.
  // Единственный регулятор затемнения находится в разделе «Внешний вид панели».
  root.style.setProperty('--dashboard-bg-opacity', backgroundSettings.enabled && backgroundSettings.url ? 1 : 0);
  const el=document.getElementById('backgroundImage');
  if(el){
    el.style.backgroundImage = backgroundSettings.enabled && backgroundSettings.url ? `url("${String(backgroundSettings.url).replaceAll('"','%22')}")` : 'none';
  }
  const preview=document.getElementById('backgroundPreview');
  if(preview){
    if(backgroundSettings.enabled && backgroundSettings.url){
      preview.style.backgroundImage=`url("${String(backgroundSettings.url).replaceAll('"','%22')}")`;
      preview.classList.add('has-background');
      preview.innerHTML='<span>Текущий фон</span>';
    }else{
      preview.style.backgroundImage='none';
      preview.classList.remove('has-background');
      preview.innerHTML='<span>Фон не установлен</span>';
    }
  }
}

async function loadBackgroundConfig(){
  try{
    const r=await fetch('/api/background',{cache:'no-store'});
    const data=await r.json();
    backgroundSettings=data;
    applyBackground(data);
  }catch(e){console.error(e)}
}

async function loadAppearanceConfig(){
  try{
    const r=await fetch('/api/appearance',{cache:'no-store'});
    const data=await r.json();
    applyAppearance(data, true);
    applyBackground(backgroundSettings);
  }catch(e){console.error(e)}
}

function syncAppearanceControls(){
  const values={
    cardOpacity: Math.round(Number(appearanceSettings.card_opacity)*100),
    cardBlur: Number(appearanceSettings.card_blur),
    backgroundBlur: Number(appearanceSettings.background_blur),
    backgroundDim: Math.round(Number(appearanceSettings.background_dim)*100)
  };
  for(const [id,value] of Object.entries(values)){
    const el=document.getElementById(id);
    const out=document.getElementById(`${id}Value`);
    if(el)el.value=value;
    if(out)out.textContent=id==='cardOpacity'||id==='backgroundDim'?`${value}%`:`${value} px`;
  }
}

function previewAppearanceControl(kind,value){
  const n=Number(value);
  if(kind==='cardOpacity')appearanceSettings.card_opacity=n/100;
  if(kind==='cardBlur')appearanceSettings.card_blur=n;
  if(kind==='backgroundBlur')appearanceSettings.background_blur=n;
  if(kind==='backgroundDim')appearanceSettings.background_dim=n/100;
  applyAppearance(appearanceSettings, true);
}

async function saveAppearanceSettings(){
  try{
    const r=await fetch('/api/appearance',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(appearanceSettings)});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Не удалось сохранить внешний вид');
    applyAppearance(data, true);
    applyBackground(backgroundSettings);
    alert('Настройки внешнего вида сохранены.');
  }catch(e){alert(e.message)}
}

async function uploadBackgroundFile(event){
  const file=event.target.files?.[0];
  event.target.value='';
  if(!file)return;
  try{
    const form=new FormData(); form.append('file',file);
    const r=await fetch('/api/background/upload',{method:'POST',body:form});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Не удалось загрузить фон');
    backgroundSettings.url=data.url;
    backgroundSettings.enabled=true;
    backgroundSettings.opacity=1;
    applyBackground(backgroundSettings);
    alert('Фоновое изображение загружено. Нажмите «Сохранить фон».');
  }catch(e){alert(e.message)}
}

async function importBackgroundFromUrl(){
  const input=document.getElementById('backgroundUrl');
  const url=input?.value.trim();
  if(!url){alert('Укажите URL изображения');return}
  try{
    const r=await fetch('/api/background/from-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Не удалось скачать фон');
    backgroundSettings.url=data.url;
    backgroundSettings.enabled=true;
    backgroundSettings.opacity=1;
    applyBackground(backgroundSettings);
    input.value='';
    alert('Фон загружен. Нажмите «Сохранить фон».');
  }catch(e){alert(e.message)}
}

async function saveBackgroundSettings(){
  backgroundSettings.opacity = 1;
  try{
    const r=await fetch('/api/background',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(backgroundSettings)});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Не удалось сохранить фон');
    applyBackground(data);
  }catch(e){alert(e.message)}
}

async function removeBackgroundImage(){
  if(!confirm('Удалить фоновое изображение?'))return;
  backgroundSettings.opacity = 1;
  try{
    const r=await fetch('/api/background',{method:'DELETE'});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Не удалось удалить фон');
    applyBackground(data);
  }catch(e){alert(e.message)}
}

function renderEmbyStatus(data){
  const panel = document.getElementById('embyPanel');
  if(!panel) return;
  if(!data || data.configured === false || data.enabled === false){
    panel.classList.add('hidden');
    panel.innerHTML='';
    return;
  }
  panel.classList.remove('hidden');
  const checked=data.checked_at ? new Date(data.checked_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '';
  if(!data.online){
    panel.innerHTML = `<div class="emby-header"><div><div class="emby-title"><span class="status-dot offline"></span> 📺 ${escapeHtml(data.name || 'Emby')}</div><div class="emby-subtitle">Сервер недоступен${checked?' · проверено '+checked:''}</div></div><button type="button" onclick="loadEmbyStatus()">↻ Обновить</button></div><div class="emby-offline"><div><strong>Офлайн</strong><div>${escapeHtml(data.error || 'Нет соединения с Emby')}</div></div></div>`;
    return;
  }
  const players = Array.isArray(data.players) ? data.players : [];
  const playerHtml = players.length ? players.map(p=>{
    const title=p.title||'Воспроизведение';
    const series=p.series?` · ${escapeHtml(p.series)}`:'';
    const method=p.play_method?` · ${escapeHtml(p.play_method)}`:'';
    const progress=Math.max(0,Math.min(100,Number(p.percent)||0));
    return `<div class="emby-player"><span class="status-dot online"></span><div class="emby-player-main"><strong>${escapeHtml(p.user)}</strong><span>${escapeHtml(title)}${series}</span><small>${escapeHtml(p.device)}${p.transcoding?' · Транскодирование':''}${p.paused?' · Пауза':''}${method}</small><div class="emby-progress"><i style="width:${progress}%"></i></div></div><span class="emby-percent">${Math.round(progress)}%</span></div>`;
  }).join('') : '<div class="emby-empty">Сейчас никто не смотрит</div>';
  panel.innerHTML = `<div class="emby-header"><div><div class="emby-title"><span class="status-dot online"></span> ${escapeHtml(data.server_name || data.name || 'Emby')}</div><div class="emby-subtitle">Emby ${escapeHtml(data.version || '')}${data.latency_ms!=null?' · '+data.latency_ms+' ms':''}${checked?' · '+checked:''}</div></div><button type="button" onclick="loadEmbyStatus()">↻ Обновить</button></div><div class="emby-stats"><div><strong>${data.sessions||0}</strong><span>сессий</span></div><div><strong>${data.playing||0}</strong><span>смотрят</span></div><div><strong>${data.transcoding||0}</strong><span>транскод.</span></div><div><strong>${data.users||0}</strong><span>пользователей</span></div></div><div class="emby-players">${playerHtml}</div>`;
}
async function loadEmbyStatus(){
  try{
    const r=await fetch('/api/emby/status',{cache:'no-store'});
    const data=await r.json();
    renderEmbyStatus(data);
  }catch(e){
    renderEmbyStatus({configured:true,enabled:true,online:false,name:'Emby',error:'Ошибка запроса к Dashboard'});
  }
}

async function testEmbyConnection(){
  const box=document.getElementById('embyTestResult');
  if(box)box.textContent='Проверяем подключение...';
  try{
    const r=await fetch('/api/emby/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:document.getElementById('embyUrl')?.value.trim()||'',api_key:document.getElementById('embyApiKey')?.value.trim()||''})});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Не удалось проверить подключение');
    if(box)box.textContent=data.online?`✅ ${data.server_name||'Emby'} · ${data.version||''}${data.latency_ms!=null?' · '+data.latency_ms+' ms':''}`:`❌ ${data.error||'Emby недоступен'}`;
  }catch(e){if(box)box.textContent=`❌ ${e.message}`}
}
function startEmbyPolling(){
  loadEmbyStatus();
  if(embyTimer)clearInterval(embyTimer);
  embyTimer=setInterval(loadEmbyStatus, 15000);
}


async function loadEmbyConfig(){
  try{
    const r=await fetch('/api/emby/config');
    const data=await r.json();
    const name=document.getElementById('embyName');
    const url=document.getElementById('embyUrl');
    const key=document.getElementById('embyApiKey');
    const enabled=document.getElementById('embyEnabled');
    if(name)name.value=data.name||'Emby';
    if(url)url.value=data.url||'';
    if(key)key.value='';
    if(enabled)enabled.checked=data.enabled!==false;
    const hint=document.getElementById('embyKeyHint');
    if(hint)hint.textContent=data.configured?'API ключ сохранён. Оставьте поле пустым, чтобы не менять его.':'API ключ нужен для получения статуса сервера.';
  }catch(e){ console.error(e); }
}

async function saveEmbyConfig(){
  const name=document.getElementById('embyName')?.value.trim()||'Emby';
  const url=document.getElementById('embyUrl')?.value.trim()||'';
  const api_key=document.getElementById('embyApiKey')?.value.trim()||'';
  const enabled=!!document.getElementById('embyEnabled')?.checked;
  try{
    const r=await fetch('/api/emby/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,url,api_key,enabled})});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Не удалось сохранить настройки Emby');
    const hint=document.getElementById('embyKeyHint');
    if(hint)hint.textContent='Настройки сохранены. API ключ хранится на сервере Dashboard и не экспортируется.';
    await loadEmbyStatus();
  }catch(e){alert(e.message)}
}

async function loadData(){
  const [cr, ar] = await Promise.all([fetch('/api/categories'), fetch('/api/apps')]);
  categories = await cr.json();
  apps = await ar.json();
  if(selectedCategory !== "all" && selectedCategory !== "favorites" && !categories.some(c => c.id === selectedCategory)) selectedCategory = "all";
  renderCategories();
  renderApps();
  fillCategorySelect();
}

function renderCategories(){
  const nav = document.getElementById('categories');
  nav.innerHTML = `
    <button class="category ${selectedCategory==='all'?'active':''}" onclick="selectCategory('all')">🏠 Все <span class="count">${apps.length}</span></button>
    <button class="category ${selectedCategory==='favorites'?'active':''}" onclick="selectCategory('favorites')">⭐ Избранное <span class="count">${apps.filter(a=>a.favorite).length}</span></button>
    ${categories.map(c=>`<button class="category ${selectedCategory===c.id?'active':''}" onclick="selectCategory(${c.id})">${iconHtml(c.icon,'category-icon')} ${escapeHtml(c.name)} <span class="count">${c.app_count}</span></button>`).join('')}`;
}

function selectCategory(id){selectedCategory=id;renderCategories();renderApps()}

function renderApps(){
  const q=(document.getElementById('search')?.value||'').toLowerCase().trim();
  if(orderEditMode && q) toggleOrderEditMode(false);
  const filtered=apps.filter(a=>{
    const cat=selectedCategory==='all'||(selectedCategory==='favorites'&&a.favorite)||a.category_id===selectedCategory;
    const s=a.name.toLowerCase().includes(q)||a.description.toLowerCase().includes(q)||a.url.toLowerCase().includes(q);
    return cat&&s;
  });
  const d=document.getElementById('dashboard');
  const qHint=orderEditMode ? '<div class="order-edit-note">↔ Перетаскивайте плитки мышкой. Порядок сохраняется автоматически.</div>' : '';
  d.innerHTML=!filtered.length
    ? '<div class="empty">В этой категории пока нет приложений</div>'
    : `<div class="group">${qHint}<div class="group-title">${escapeHtml(currentTitle())}</div><div class="grid">${filtered.map(appCard).join('')}</div></div>`;
}

function currentTitle(){if(selectedCategory==='all')return'Все приложения';if(selectedCategory==='favorites')return'Избранное';return categories.find(c=>c.id===selectedCategory)?.name||''}

function appCard(a){
  const size = ['small','medium','large'].includes(a.size) ? a.size : 'medium';
  const dragAttrs = orderEditMode ? `draggable="true" ondragstart="dragStartApp(event,${a.id})" ondragover="dragOverApp(event)" ondragleave="dragLeaveApp(event)" ondrop="dropApp(event,${a.id})" ondragend="dragEndApp(event)"` : '';
  const dragHandle = orderEditMode ? '<span class="drag-handle" title="Перетащить">⠿</span>' : '';
  const moveActions = orderEditMode ? `<button title="Переместить вверх" onclick="moveAppByStep(event,${a.id},-1)">↑</button><button title="Переместить вниз" onclick="moveAppByStep(event,${a.id},1)">↓</button>` : '';
  return `<article class="app-card size-${size}${orderEditMode?' order-editing':''}" data-app-id="${a.id}" ${dragAttrs} onclick="openApp(${a.id})">
    ${dragHandle}
    ${a.favorite?'<div class="favorite">⭐</div>':''}
    <div class="icon">${iconHtml(a.icon,'app-card-icon')}</div>
    <div class="app-name">${escapeHtml(a.name)}</div>
    <div class="app-description">${escapeHtml(a.description||a.url)}</div>
    <div class="actions" onclick="event.stopPropagation()">${moveActions}<button onclick="editApp(${a.id})">Изменить</button><button onclick="deleteApp(${a.id})">Удалить</button></div>
  </article>`;
}

function openApp(id){if(orderEditMode)return;const a=apps.find(x=>x.id===id);if(a)window.open(a.url,'_blank','noopener,noreferrer')}

function toggleOrderEditMode(force){
  const search=(document.getElementById('search')?.value||'').trim();
  if(force === true && search){
    alert('Очистите поиск, чтобы изменять порядок плиток.');
    return;
  }
  orderEditMode = typeof force === 'boolean' ? force : !orderEditMode;
  const button=document.getElementById('orderEditButton');
  if(button){
    button.textContent=orderEditMode?'✅ Готово':'↔ Порядок';
    button.classList.toggle('primary',orderEditMode);
  }
  const hint=document.getElementById('orderEditHint');
  if(hint)hint.textContent=orderEditMode?'Перетаскивание включено — порядок сохраняется автоматически.':'';
  renderApps();
}

function dragStartApp(event,id){
  if(!orderEditMode)return;
  dragAppId=id;
  event.dataTransfer.effectAllowed='move';
  event.dataTransfer.setData('text/plain',String(id));
  event.currentTarget.classList.add('dragging');
}

function dragOverApp(event){
  if(!orderEditMode || dragAppId===null)return;
  event.preventDefault();
  event.dataTransfer.dropEffect='move';
  const target=event.currentTarget;
  if(Number(target.dataset.appId)!==dragAppId)target.classList.add('drop-target');
}

function dragLeaveApp(event){
  event.currentTarget.classList.remove('drop-target');
}

async function dropApp(event,targetId){
  if(!orderEditMode || dragAppId===null)return;
  event.preventDefault();
  const target=event.currentTarget;
  target.classList.remove('drop-target');
  const sourceId=dragAppId;
  dragAppId=null;
  if(sourceId===targetId)return;

  const grid=target.closest('.grid');
  if(!grid)return;
  const visibleIds=[...grid.querySelectorAll('.app-card')].map(el=>Number(el.dataset.appId));
  const sourceIndex=visibleIds.indexOf(sourceId);
  const targetIndex=visibleIds.indexOf(targetId);
  if(sourceIndex<0 || targetIndex<0)return;
  visibleIds.splice(sourceIndex,1);
  const targetPosition=visibleIds.indexOf(targetId);
  const rect=target.getBoundingClientRect();
  const after=event.clientX > rect.left + rect.width/2;
  visibleIds.splice(targetPosition + (after?1:0),0,sourceId);
  await saveVisibleAppOrder(visibleIds);
}

function dragEndApp(event){
  event.currentTarget.classList.remove('dragging','drop-target');
  document.querySelectorAll('.app-card.drop-target').forEach(el=>el.classList.remove('drop-target'));
  dragAppId=null;
}

async function saveVisibleAppOrder(visibleIds){
  const visibleSet=new Set(visibleIds);
  let cursor=0;
  const fullIds=apps.map(a=>a.id).map(id=>visibleSet.has(id)?visibleIds[cursor++]:id);
  const r=await fetch('/api/apps/reorder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:fullIds})});
  if(!r.ok){alert((await r.json()).detail||'Не удалось сохранить порядок');return}
  const byId=new Map(apps.map(a=>[a.id,a]));
  apps=fullIds.map(id=>byId.get(id)).filter(Boolean);
  renderApps();
}

async function moveAppByStep(event,id,step){
  event.stopPropagation();
  if(!orderEditMode)return;
  const grid=event.currentTarget.closest('.grid');
  if(!grid)return;
  const ids=[...grid.querySelectorAll('.app-card')].map(el=>Number(el.dataset.appId));
  const index=ids.indexOf(id);
  const next=index+step;
  if(index<0 || next<0 || next>=ids.length)return;
  [ids[index],ids[next]]=[ids[next],ids[index]];
  await saveVisibleAppOrder(ids);
}
function fillCategorySelect(){document.getElementById('categoryId').innerHTML=categories.map(c=>`<option value="${c.id}">${iconHtml(c.icon,'select-icon')} ${escapeHtml(c.name)}</option>`).join('')}

const appIcons=['🚀','🎬','🎥','💻','🌐','📁','🛠️','⚙️','📊','📈','🎮','🎵','📷','📝','📚','🔧','🧰','🗂️','⭐','❤️','🔥','💡','🔐','🖥️','📦','🐳','🧪','🛰️','🗃️','🖱️','⌨️','🧩','🛒','☁️','📌','🔗','📰','🎨','🎧','📱','🖨️','💾','🛍️','🏢','🏡','🚗','✈️','🗺️','💰','📅','✅','❗','❓','🔔'];
const categoryIcons=['📁','🚀','🛠️','📊','💻','🌐','🎮','🎵','🎬','📚','💼','🏠','⭐','🔥','⚙️','🔧','🧰','🗂️','📈','💡','🧪','📌','🔗','📰','🎨','📱','🏢','🏡','🗺️','💰'];

function iconHtml(value, className=''){
  const v=String(value??'').trim();
  if(v.startsWith('/icons/')) return `<img class="${className} icon-image" src="${escapeHtml(v)}" alt="" loading="lazy">`;
  return `<span class="${className}">${escapeHtml(v||'—')}</span>`;
}

function renderIconChoices(containerId,inputId,icons){
  const el=document.getElementById(containerId);
  if(!el)return;
  el.innerHTML=icons.map(icon=>`<button type="button" class="icon-choice" data-icon="${escapeHtml(icon)}" title="Выбрать ${escapeHtml(icon)}" onclick="setIcon('${inputId}','${containerId}','${icon}')">${icon}</button>`).join('');
  syncIconPicker(inputId,containerId);
}

function setIcon(inputId,containerId,icon){
  const input=document.getElementById(inputId);
  if(!input)return;
  input.value=icon;
  syncIconPicker(inputId,containerId);
  input.focus();
}

function syncIconPicker(inputId,containerId){
  const input=document.getElementById(inputId);
  const container=document.getElementById(containerId);
  if(!input||!container)return;
  const value=input.value.trim();
  container.querySelectorAll('.icon-choice').forEach(btn=>btn.classList.toggle('selected',btn.dataset.icon===value));
  const preview=document.getElementById(inputId==='icon'?'appIconPreview':'categoryIconPreview');
  if(preview)preview.innerHTML=iconHtml(value,'preview-image');
  const state=document.getElementById(inputId==='icon'?'appIconSourceStatus':'categoryIconSourceStatus');
  if(state)state.textContent=value.startsWith('/icons/')?'Локальная иконка сохранена':(value?'Emoji / текстовый значок':'Иконка не выбрана');
}

function clearIcon(inputId,containerId){
  const input=document.getElementById(inputId);
  if(!input)return;
  input.value='';
  syncIconPicker(inputId,containerId);
  input.focus();
}

async function uploadIconFile(inputId,containerId,statusId,event){
  const file=event.target.files?.[0];
  event.target.value='';
  if(!file)return;
  const status=document.getElementById(statusId);
  if(status)status.textContent='Загрузка...';
  try{
    const form=new FormData();
    form.append('file',file);
    const r=await fetch('/api/icons/upload',{method:'POST',body:form});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Не удалось загрузить иконку');
    document.getElementById(inputId).value=data.icon;
    syncIconPicker(inputId,containerId);
  }catch(e){
    if(status)status.textContent='Ошибка загрузки';
    alert(e.message);
  }
}

async function importIconFromUrl(inputId,containerId,urlInputId,statusId){
  const url=document.getElementById(urlInputId)?.value.trim();
  const status=document.getElementById(statusId);
  if(!url){alert('Укажите URL изображения');return}
  if(status)status.textContent='Скачивание...';
  try{
    const r=await fetch('/api/icons/from-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Не удалось скачать иконку');
    document.getElementById(inputId).value=data.icon;
    syncIconPicker(inputId,containerId);
    document.getElementById(urlInputId).value='';
  }catch(e){
    if(status)status.textContent='Ошибка загрузки';
    alert(e.message);
  }
}

async function findFavicon(inputId,containerId,siteUrlInputId,statusId){
  const url=document.getElementById(siteUrlInputId)?.value.trim();
  const status=document.getElementById(statusId);
  if(!url){alert('Сначала укажите URL приложения');return}
  if(status)status.textContent='Поиск favicon...';
  try{
    const r=await fetch('/api/icons/favicon',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'Favicon не найден');
    document.getElementById(inputId).value=data.icon;
    syncIconPicker(inputId,containerId);
  }catch(e){
    if(status)status.textContent='Favicon не найден';
    alert(e.message);
  }
}

function updateTileSizePreview(){
  const value=document.getElementById('tileSize')?.value||'medium';
  document.querySelectorAll('.tile-size-demo').forEach(el=>el.classList.remove('active'));
  const selected=document.querySelector(`.tile-size-demo-${value}`);
  if(selected)selected.classList.add('active');
}

function openAppModal(a=null){
  document.getElementById('modal').classList.remove('hidden');
  document.getElementById('modalTitle').textContent=a?'Изменить приложение':'Добавить приложение';
  document.getElementById('appId').value=a?.id||'';
  document.getElementById('name').value=a?.name||'';
  document.getElementById('url').value=a?.url||'';
  document.getElementById('description').value=a?.description||'';
  document.getElementById('icon').value=a?.icon||'🚀';
  document.getElementById('appIconUrl').value='';
  renderIconChoices('appIconChoices','icon',appIcons);
  document.getElementById('favorite').checked=!!a?.favorite;
  document.getElementById('tileSize').value=['small','medium','large'].includes(a?.size)?a.size:'medium';
  fillCategorySelect();
  if(a)document.getElementById('categoryId').value=a.category_id;
  else if(typeof selectedCategory==='number')document.getElementById('categoryId').value=selectedCategory;
  updateTileSizePreview();
}

function closeModal(){document.getElementById('modal').classList.add('hidden')}
function editApp(id){const a=apps.find(x=>x.id===id);if(a)openAppModal(a)}

async function saveApp(e){
  e.preventDefault();
  const id=document.getElementById('appId').value;
  const item={
    name:document.getElementById('name').value.trim(),
    url:document.getElementById('url').value.trim(),
    description:document.getElementById('description').value.trim(),
    category_id:Number(document.getElementById('categoryId').value),
    icon:document.getElementById('icon').value.trim()||'🚀',
    favorite:document.getElementById('favorite').checked,
    size:document.getElementById('tileSize').value
  };
  const r=await fetch(id?`/api/apps/${id}`:'/api/apps',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});
  if(!r.ok){alert((await r.json()).detail||'Ошибка сохранения');return}
  closeModal();
  await loadData();
}

function openCategoryModal(c=null){
  document.getElementById('categoryModal').classList.remove('hidden');
  document.getElementById('categoryModalTitle').textContent=c?'Изменить категорию':'Создать категорию';
  document.getElementById('categoryEditId').value=c?.id||'';
  document.getElementById('categoryName').value=c?.name||'';
  document.getElementById('categoryIcon').value=c?.icon||'📁';
  document.getElementById('categoryIconUrl').value='';
  renderIconChoices('categoryIconChoices','categoryIcon',categoryIcons);
}

function closeCategoryModal(){document.getElementById('categoryModal').classList.add('hidden')}

async function saveCategory(e){
  e.preventDefault();
  const id=document.getElementById('categoryEditId').value;
  const item={name:document.getElementById('categoryName').value.trim(),icon:document.getElementById('categoryIcon').value.trim()||'📁'};
  const r=await fetch(id?`/api/categories/${id}`:'/api/categories',{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});
  if(!r.ok){alert((await r.json()).detail||'Ошибка сохранения категории');return}
  closeCategoryModal();
  await loadData();
  if(!id){const c=categories.find(x=>x.name===item.name);if(c)selectCategory(c.id)}
}

function editSelectedCategory(){
  if(typeof selectedCategory!=='number'){alert('Сначала выберите категорию');return}
  const c=categories.find(x=>x.id===selectedCategory);if(c)openCategoryModal(c)
}

async function deleteSelectedCategory(){
  if(typeof selectedCategory!=='number'){alert('Сначала выберите категорию');return}
  const c=categories.find(x=>x.id===selectedCategory);
  if(!c||!confirm(`Удалить категорию «${c.name}»?`))return;
  const r=await fetch(`/api/categories/${c.id}`,{method:'DELETE'});
  if(!r.ok){alert((await r.json()).detail||'Категорию нельзя удалить');return}
  selectedCategory='all';
  await loadData();
}

async function deleteApp(id){
  const a=apps.find(x=>x.id===id);
  if(!a||!confirm(`Удалить «${a.name}»?`))return;
  await fetch(`/api/apps/${id}`,{method:'DELETE'});
  await loadData();
}

function openSettingsModal(){const modal=document.getElementById('settingsModal');if(modal)modal.classList.remove('hidden');applyTheme(currentTheme,false);syncAppearanceControls();loadEmbyConfig();loadBackgroundConfig();loadAppearanceConfig()}
function closeSettingsModal(){const modal=document.getElementById('settingsModal');if(modal)modal.classList.add('hidden');const file=document.getElementById('settingsFile');if(file)file.value=''}

async function exportSettings(){
  const r=await fetch('/api/settings/export?theme='+encodeURIComponent(currentTheme));
  if(!r.ok){alert('Не удалось подготовить настройки');return}
  const data=await r.json();
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;
  a.download='My-DashboardKDV-settings.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function importSettingsFile(event){
  const file=event.target.files?.[0];
  if(!file)return;
  try{
    const text=await file.text();
    const data=JSON.parse(text);
    if(!Array.isArray(data.categories)||!Array.isArray(data.apps))throw new Error('Неверный формат файла');
    if(data.theme)applyTheme(data.theme);
    if(!confirm('Импортировать настройки? Текущие приложения и категории будут заменены данными из файла.')){event.target.value='';return}
    const r=await fetch('/api/settings/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result=await r.json();
    if(!r.ok)throw new Error(result.detail||'Ошибка импорта');
    selectedCategory='all';
    closeSettingsModal();
    await loadData();
    await loadBackgroundConfig();
    await loadAppearanceConfig();
    alert(`Настройки импортированы: ${result.categories} категорий, ${result.apps} приложений.`);
  }catch(e){alert(`Не удалось импортировать настройки: ${e.message}`)}finally{event.target.value=''}
}

function escapeHtml(v){return String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;')}

document.addEventListener('DOMContentLoaded',()=>{
  applyTheme(currentTheme,false);
  const settingsButton=document.getElementById('settingsButton');
  if(settingsButton)settingsButton.addEventListener('click',openSettingsModal);
  const settingsModal=document.getElementById('settingsModal');
  if(settingsModal)settingsModal.addEventListener('click',event=>{if(event.target===settingsModal)closeSettingsModal()});
  const themeToggle=document.getElementById('themeToggle');
  if(themeToggle)themeToggle.addEventListener('click',toggleTheme);
  const themeSelect=document.getElementById('themeSelect');
  if(themeSelect)themeSelect.addEventListener('change',e=>applyTheme(e.target.value));
  const orderEditButton=document.getElementById('orderEditButton');
  if(orderEditButton)orderEditButton.addEventListener('click',()=>toggleOrderEditMode());
  const tileSize=document.getElementById('tileSize');
  if(tileSize)tileSize.addEventListener('change',updateTileSizePreview);
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeSettingsModal();closeModal();closeCategoryModal()}});
  loadData().catch(e=>{console.error(e);document.getElementById('dashboard').innerHTML='<div class="empty">Ошибка загрузки Dashboard</div>'});
  loadBackgroundConfig();
  loadAppearanceConfig();
  startEmbyPolling();
});
