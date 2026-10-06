let apps = [], categories = [], selectedCategory = "all", embyTimer = null;
let panelEditMode = false, dragAppId = null, dragCategoryId = null;
let draftAppOrder = null, draftCategoryOrder = null, draftAppChanges = new Map();
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
  if(persist){ localStorage.setItem('mdkdv-theme', currentTheme); persistTheme(); }
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

async function loadPreferences(){
  try{
    const r=await fetch('/api/preferences',{cache:'no-store'});
    if(!r.ok)return;
    const data=await r.json();
    if(data?.theme==='light'||data?.theme==='dark'){
      currentTheme=data.theme;
      localStorage.setItem('mdkdv-theme', currentTheme);
      applyTheme(currentTheme,false);
    }
  }catch(e){console.error(e)}
}

async function loadData(){
  const [cr, ar] = await Promise.all([fetch('/api/categories', {cache:'no-store'}), fetch('/api/apps', {cache:'no-store'})]);
  const categoryData = await cr.json().catch(()=>[]);
  const appData = await ar.json().catch(()=>[]);
  if(!cr.ok) throw new Error(categoryData?.detail || `Ошибка загрузки категорий (${cr.status})`);
  if(!ar.ok) throw new Error(appData?.detail || `Ошибка загрузки приложений (${ar.status})`);
  categories = Array.isArray(categoryData) ? categoryData.map(c=>({
    ...c,
    id:Number(c.id),
    name:String(c.name ?? ''),
    icon:String(c.icon ?? '📁'),
    sort_order:Number(c.sort_order ?? 0),
    app_count:Number(c.app_count ?? 0)
  })) : [];
  apps = Array.isArray(appData) ? appData.map(a => ({
    ...a,
    id:Number(a.id),
    name:String(a.name ?? ''),
    url:String(a.url ?? ''),
    description:String(a.description ?? ''),
    category_id:Number(a.category_id),
    icon:String(a.icon ?? '🚀'),
    favorite:Boolean(a.favorite),
    open_mode: a.open_mode === 'embedded' ? 'embedded' : 'external',
    size:['mini','small','medium','wide','tall','large','xl','hero'].includes(a.size)?a.size:'medium',
    tile_bg_mode: ['default','color','image'].includes(a.tile_bg_mode) ? a.tile_bg_mode : 'default',
    tile_bg_value: String(a.tile_bg_value || '').trim(),
    tile_bg_scale: Math.round(clampNumber(a.tile_bg_scale,50,200,100))
  })) : [];
  if(selectedCategory !== "all" && selectedCategory !== "favorites" && !categories.some(c => c.id === selectedCategory)) selectedCategory = "all";
  renderCategories();
  renderApps();
  fillCategorySelect();
}

function renderCategories(){
  const nav = document.getElementById('categories');
  if(!nav)return;
  const ordered = panelEditMode && Array.isArray(draftCategoryOrder)
    ? draftCategoryOrder.map(id=>categories.find(c=>c.id===id)).filter(Boolean)
    : [...categories].sort((a,b)=>(Number(a.sort_order||0)-Number(b.sort_order||0))||(a.id-b.id));
  nav.classList.toggle('category-editing',panelEditMode);
  nav.innerHTML = `
    <button class="category ${selectedCategory==='all'?'active':''}" onclick="selectCategory('all')">🏠 Все <span class="count">${apps.length}</span></button>
    <button class="category ${selectedCategory==='favorites'?'active':''}" onclick="selectCategory('favorites')">⭐ Избранное <span class="count">${apps.filter(a=>a.favorite).length}</span></button>
    ${ordered.map(c=>{
      const drag = panelEditMode ? ` draggable="true" ondragstart="dragStartCategory(event,${c.id})" ondragover="dragOverCategory(event)" ondragleave="dragLeaveCategory(event)" ondrop="dropCategory(event,${c.id})" ondragend="dragEndCategory(event)"` : '';
      const grip = panelEditMode ? '<span class="category-grip" title="Перетащить">⠿</span>' : '';
      return `<button class="category ${selectedCategory===c.id?'active':''}${panelEditMode?' category-editing-item':''}" data-category-id="${c.id}" onclick="selectCategory(${c.id})"${drag}>${grip}${iconHtml(c.icon,'category-icon')} ${escapeHtml(c.name)} <span class="count">${c.app_count}</span></button>`;
    }).join('')}`;
}

function selectCategory(id){selectedCategory=id;renderCategories();renderApps()}

function renderApps(){
  const q=(document.getElementById('search')?.textContent||'').toLowerCase().trim();
  if(panelEditMode && q) cancelPanelEditMode();
  const filtered=apps.filter(a=>{
    const cat=selectedCategory==='all'||(selectedCategory==='favorites'&&a.favorite)||a.category_id===selectedCategory;
    const s=a.name.toLowerCase().includes(q)||a.description.toLowerCase().includes(q)||a.url.toLowerCase().includes(q);
    return cat&&s;
  });
  const d=document.getElementById('dashboard');
  const qHint=panelEditMode ? '<div class="order-edit-note">✏️ Режим редактирования: перетаскивайте приложения и категории. Нажмите «Сохранить макет».</div>' : '';
  const orderedFiltered = panelEditMode && Array.isArray(draftAppOrder)
    ? draftAppOrder.map(id=>apps.find(a=>a.id===id)).filter(Boolean).filter(a=>filtered.some(f=>f.id===a.id))
    : filtered;
  d.innerHTML=!orderedFiltered.length
    ? '<div class="empty">В этой категории пока нет приложений</div>'
    : `<div class="group">${qHint}<div class="group-title">${escapeHtml(currentTitle())}</div><div class="grid ${panelEditMode?'edit-grid':''}">${orderedFiltered.map(appCard).join('')}</div></div>`;
}

function currentTitle(){if(selectedCategory==='all')return'Все приложения';if(selectedCategory==='favorites')return'Избранное';return categories.find(c=>c.id===selectedCategory)?.name||''}

function clampNumber(value,min,max,fallback){
  const n=Number(value);
  if(!Number.isFinite(n))return fallback;
  return Math.max(min,Math.min(max,n));
}

function hexToRgb(value){
  const m=String(value||'').trim().match(/^#([0-9a-f]{6})$/i);
  if(!m)return null;
  const hex=m[1];
  return `${parseInt(hex.slice(0,2),16)},${parseInt(hex.slice(2,4),16)},${parseInt(hex.slice(4,6),16)}`;
}

function safeCssColor(value){
  return /^#[0-9a-f]{6}$/i.test(String(value||'')) ? String(value) : '#ffffff';
}

function safeCssUrl(value){
  return String(value||'').replaceAll('\\','%5C').replaceAll('"','%22').replaceAll("'",'%27').replaceAll('\n','').replaceAll('\r','');
}

function tileStyle(a){
  const opacity=clampNumber(a.tile_opacity,0.45,1,0.90);
  const blur=clampNumber(a.tile_blur,0,20,6);
  const iconSize=clampNumber(a.tile_icon_size,24,96,48);
  const titleSize=clampNumber(a.tile_title_size,12,28,17);
  const titleColor=/^#[0-9a-f]{6}$/i.test(String(a.tile_title_color||''))?String(a.tile_title_color):'#ffffff';
  const descriptionColor=/^#[0-9a-f]{6}$/i.test(String(a.tile_description_color||''))?String(a.tile_description_color):'#cbd5e1';
  const urlColor=/^#[0-9a-f]{6}$/i.test(String(a.tile_url_color||''))?String(a.tile_url_color):'#94a3b8';
  const bgMode=['default','color','image'].includes(a.tile_bg_mode)?a.tile_bg_mode:'default';
  const bgValue=String(a.tile_bg_value||'').trim();
  const bgScale=Math.round(clampNumber(a.tile_bg_scale,50,200,100));
  const rgb=getComputedStyle(document.documentElement).getPropertyValue('--card-rgb').trim()||'25,29,39';
  let backgroundColor=`rgba(${rgb},${opacity})`;
  let imageVars='--tile-bg-image:none;--tile-bg-opacity:1;--tile-bg-size:100%;';
  if(bgMode==='color'){
    const colorRgb=hexToRgb(bgValue)||rgb;
    backgroundColor=`rgba(${colorRgb},${opacity})`;
  }else if(bgMode==='image' && bgValue){
    imageVars=`--tile-bg-image:url("${safeCssUrl(bgValue)}");--tile-bg-opacity:${opacity};--tile-bg-scale:${bgScale/100};`;
    backgroundColor=`rgba(${rgb},1)`;
  }
  return `style="background-color:${backgroundColor};backdrop-filter:blur(${blur}px);-webkit-backdrop-filter:blur(${blur}px);--tile-blur:${blur}px;--tile-icon-size:${iconSize}px;--tile-title-size:${titleSize}px;--tile-title-color:${safeCssColor(titleColor)};--tile-description-color:${safeCssColor(descriptionColor)};--tile-url-color:${safeCssColor(urlColor)};${imageVars}"`;
}

function appCard(a){
  const size = ['mini','small','medium','wide','tall','large','xl','hero'].includes(a.size) ? a.size : 'medium';
  const dragAttrs = panelEditMode ? `draggable="true" ondragstart="dragStartApp(event,${a.id})" ondragover="dragOverApp(event)" ondragleave="dragLeaveApp(event)" ondrop="dropApp(event,${a.id})" ondragend="dragEndApp(event)"` : '';
  const dragHandle = panelEditMode ? '<span class="drag-handle" title="Перетащить">⠿</span>' : '';
  const moveActions = panelEditMode ? `<button title="Переместить вверх" onclick="moveAppByStep(event,${a.id},-1)">↑</button><button title="Переместить вниз" onclick="moveAppByStep(event,${a.id},1)">↓</button>` : '';
  const editorActions = panelEditMode ? `<button title="Размер" onclick="quickResizeApp(event,${a.id})">📐</button><button title="Дублировать" onclick="duplicateApp(event,${a.id})">📋</button>` : '';
  const description = String(a.description||'').trim();
  const url = String(a.url||'').trim();
  const showDescription = a.tile_show_description === undefined ? true : !!a.tile_show_description;
  const showUrl = !!a.tile_show_url;
  const details = [];
  if(showDescription && description)details.push(`<div class="app-description">${escapeHtml(description)}</div>`);
  if(showUrl && url)details.push(`<div class="app-url">${escapeHtml(url)}</div>`);
  const bgValue=String(a.tile_bg_value||'').trim();
  const bgScale=Math.round(clampNumber(a.tile_bg_scale,50,200,100));
  const hasImageBg=a.tile_bg_mode==='image' && !!bgValue;
  const openBadge=a.open_mode==='embedded' ? '<span class="app-open-badge" title="Открывается внутри Dashboard">▣</span>' : '';
  const bgClass=hasImageBg?' tile-image-background':'';
  const tileBackground=hasImageBg ? `<img class="tile-background-layer" src="${escapeAttr(bgValue)}" alt="" aria-hidden="true" loading="eager" decoding="async" style="width:${bgScale}%;height:${bgScale}%;" onerror="this.style.display='none'">` : '';
  return `<article class="app-card size-${size}${bgClass}${panelEditMode?' order-editing':''}" data-app-id="${a.id}" ${dragAttrs} ${tileStyle(a)} onclick="openApp(${a.id})">
    ${tileBackground}
    ${dragHandle}
    ${a.favorite?'<div class="favorite">⭐</div>':''}${openBadge}
    <div class="icon" style="width:${clampNumber(a.tile_icon_size,24,96,48)}px;height:${clampNumber(a.tile_icon_size,24,96,48)}px;font-size:${Math.max(18,Math.round(clampNumber(a.tile_icon_size,24,96,48)*.52))}px;"><div class="app-card-icon-wrap">${iconHtml(a.icon,'app-card-icon')}</div></div>
    <div class="app-name" style="font-size:${clampNumber(a.tile_title_size,12,28,17)}px;">${escapeHtml(a.name)}</div>
    ${details.join('')}
    <div class="actions" onclick="event.stopPropagation()">${moveActions}${editorActions}<button onclick="editApp(${a.id})">Изменить</button><button onclick="deleteApp(${a.id})">Удалить</button></div>
  </article>`;
}

function openApp(id){
  if(panelEditMode)return;
  const a=apps.find(x=>x.id===id);
  if(!a || !a.url)return;
  if(a.open_mode==='embedded') openEmbeddedApp(a);
  else window.open(a.url,'_blank','noopener,noreferrer');
}

function openEmbeddedApp(a){
  const modal=document.getElementById('embeddedAppModal');
  const frame=document.getElementById('embeddedAppFrame');
  const title=document.getElementById('embeddedAppTitle');
  const external=document.getElementById('embeddedAppExternal');
  const loading=document.getElementById('embeddedAppLoading');
  if(!modal||!frame)return;
  title.textContent=a.name||'Приложение';
  external.href=a.url;
  loading.classList.add('hidden');
  modal.classList.remove('hidden');
  document.body.classList.add('embedded-open');
  frame.dataset.originalUrl=a.url;
  frame.src='about:blank';
  (async()=>{
    try{
      const r=await fetch('/api/embedded/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:a.url})});
      const data=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(data.detail||'Не удалось открыть встроенное приложение');
      frame.src=data.url;
    }catch(e){
      loading.classList.add('hidden');
      alert(e.message);
    }
  })();
  // Some embedded apps (including login flows) do not reliably trigger the
  // expected load transition for the loading overlay. Never leave the overlay
  // stuck on top of a usable application.
  window.clearTimeout(window.__embeddedLoadTimeout);
  window.__embeddedLoadTimeout=window.setTimeout(embeddedFrameLoaded, 1500);
}

function closeEmbeddedApp(){
  window.clearTimeout(window.__embeddedLoadTimeout);
  const modal=document.getElementById('embeddedAppModal');
  const frame=document.getElementById('embeddedAppFrame');
  if(modal)modal.classList.add('hidden');
  if(frame)frame.src='about:blank';
  document.body.classList.remove('embedded-open');
}

function reloadEmbeddedApp(){
  const frame=document.getElementById('embeddedAppFrame');
  const loading=document.getElementById('embeddedAppLoading');
  if(!frame)return;
  const source=frame.dataset.originalUrl||'';
  loading?.classList.add('hidden');
  frame.src='about:blank';
  if(!source)return;
  fetch('/api/embedded/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:source})})
    .then(r=>r.json().then(data=>({ok:r.ok,data})))
    .then(({ok,data})=>{if(!ok)throw new Error(data.detail||'Не удалось обновить встроенное приложение');frame.src=data.url;window.clearTimeout(window.__embeddedLoadTimeout);window.__embeddedLoadTimeout=window.setTimeout(embeddedFrameLoaded,1500);})
    .catch(e=>{loading?.classList.add('hidden');alert(e.message)});
}

function embeddedFrameLoaded(){
  document.getElementById('embeddedAppLoading')?.classList.add('hidden');
}

function handleEmbeddedEscape(event){
  if(event.key==='Escape' && !document.getElementById('embeddedAppModal')?.classList.contains('hidden')) closeEmbeddedApp();
}


function togglePanelEditMode(force){
  if(typeof force==='boolean' && force===false){
    cancelPanelEditMode();
    return;
  }
  if(panelEditMode){ savePanelLayout(); return; }
  panelEditMode=true;
  draftAppOrder=apps.map(a=>a.id);
  draftCategoryOrder=[...categories].sort((a,b)=>(Number(a.sort_order||0)-Number(b.sort_order||0))||(a.id-b.id)).map(c=>c.id);
  draftAppChanges=new Map();
  updatePanelEditControls();
  renderCategories();
  renderApps();
}

function updatePanelEditControls(){
  const button=document.getElementById('panelEditButton');
  const cancel=document.getElementById('panelEditCancel');
  if(button){button.textContent=panelEditMode?'💾 Сохранить макет':'✏️ Редактировать';button.classList.toggle('primary',panelEditMode);}
  if(cancel)cancel.classList.toggle('hidden',!panelEditMode);
}

async function savePanelLayout(){
  if(!panelEditMode)return;
  try{
    for(const [id,change] of draftAppChanges.entries()){
      const a=apps.find(x=>x.id===id);
      if(!a)continue;
      const payload={
        name:a.name,url:a.url,description:a.description,category_id:a.category_id,icon:a.icon,favorite:!!a.favorite,
        size:change.size||a.size,status_enabled:a.status_enabled!==false,
        tile_bg_mode:a.tile_bg_mode||'default',tile_bg_value:a.tile_bg_value||'',tile_bg_scale:Math.round(clampNumber(a.tile_bg_scale,50,200,100)),
        tile_opacity:Number.isFinite(Number(a.tile_opacity))?Number(a.tile_opacity):0.90,
        tile_blur:Number.isFinite(Number(a.tile_blur))?Number(a.tile_blur):6,
        tile_icon_size:Math.round(clampNumber(a.tile_icon_size,24,96,48)),
        tile_title_size:Math.round(clampNumber(a.tile_title_size,12,28,17)),
        tile_title_color:/^#[0-9a-f]{6}$/i.test(String(a.tile_title_color||''))?a.tile_title_color:'#ffffff',
        tile_description_color:/^#[0-9a-f]{6}$/i.test(String(a.tile_description_color||''))?a.tile_description_color:'#cbd5e1',
        tile_url_color:/^#[0-9a-f]{6}$/i.test(String(a.tile_url_color||''))?a.tile_url_color:'#94a3b8',
        tile_show_description:a.tile_show_description!==false,
        tile_show_url:!!a.tile_show_url
      };
      const r=await fetch(`/api/apps/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      if(!r.ok)throw new Error((await r.json()).detail||`Не удалось сохранить размер приложения «${a.name}»`);
    }
    if(Array.isArray(draftAppOrder)){
      const r=await fetch('/api/apps/reorder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:draftAppOrder})});
      if(!r.ok)throw new Error((await r.json()).detail||'Не удалось сохранить порядок приложений');
    }
    if(Array.isArray(draftCategoryOrder)){
      const r=await fetch('/api/categories/reorder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:draftCategoryOrder})});
      if(!r.ok)throw new Error((await r.json()).detail||'Не удалось сохранить порядок категорий');
    }
    const appMap=new Map(apps.map(a=>[a.id,a]));
    apps=draftAppOrder.map(id=>appMap.get(id)).filter(Boolean);
    const catMap=new Map(categories.map(c=>[c.id,c]));
    categories=draftCategoryOrder.map(id=>catMap.get(id)).filter(Boolean).map((c,i)=>({...c,sort_order:i}));
    panelEditMode=false;draftAppOrder=null;draftCategoryOrder=null;draftAppChanges=new Map();dragAppId=null;dragCategoryId=null;
    updatePanelEditControls();renderCategories();renderApps();
    alert('Макет сохранён.');
  }catch(e){alert(e.message)}
}

function cancelPanelEditMode(){
  panelEditMode=false;draftAppOrder=null;draftCategoryOrder=null;draftAppChanges=new Map();dragAppId=null;dragCategoryId=null;
  updatePanelEditControls();renderCategories();renderApps();
}

function dragStartApp(event,id){
  if(!panelEditMode)return;
  dragAppId=id;event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',String(id));event.currentTarget.classList.add('dragging');
}
function dragOverApp(event){
  if(!panelEditMode||dragAppId===null)return;
  event.preventDefault();event.dataTransfer.dropEffect='move';
  const target=event.currentTarget;if(Number(target.dataset.appId)!==dragAppId)target.classList.add('drop-target');
}
function dragLeaveApp(event){event.currentTarget.classList.remove('drop-target');}
function dropApp(event,targetId){
  if(!panelEditMode||dragAppId===null)return;
  event.preventDefault();event.currentTarget.classList.remove('drop-target');
  const sourceId=dragAppId;dragAppId=null;if(sourceId===targetId)return;
  const grid=event.currentTarget.closest('.grid');if(!grid)return;
  const visibleIds=[...grid.querySelectorAll('.app-card')].map(el=>Number(el.dataset.appId));
  const sourceIndex=visibleIds.indexOf(sourceId),targetIndex=visibleIds.indexOf(targetId);
  if(sourceIndex<0||targetIndex<0)return;
  visibleIds.splice(sourceIndex,1);
  const rect=event.currentTarget.getBoundingClientRect();
  const after=event.clientX > rect.left+rect.width/2;
  const pos=visibleIds.indexOf(targetId)+(after?1:0);visibleIds.splice(pos,0,sourceId);
  const set=new Set(visibleIds);let cursor=0;
  draftAppOrder=draftAppOrder.map(id=>set.has(id)?visibleIds[cursor++]:id);
  renderApps();
}
function dragEndApp(event){event.currentTarget.classList.remove('dragging','drop-target');document.querySelectorAll('.app-card.drop-target').forEach(el=>el.classList.remove('drop-target'));dragAppId=null;}

function moveAppByStep(event,id,step){
  event.stopPropagation();if(!panelEditMode)return;
  const index=draftAppOrder.indexOf(id),next=index+step;if(index<0||next<0||next>=draftAppOrder.length)return;
  [draftAppOrder[index],draftAppOrder[next]]=[draftAppOrder[next],draftAppOrder[index]];renderApps();
}

function dragStartCategory(event,id){
  if(!panelEditMode)return;
  dragCategoryId=id;event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/category',String(id));event.currentTarget.classList.add('dragging');
}
function dragOverCategory(event){
  if(!panelEditMode||dragCategoryId===null)return;event.preventDefault();event.dataTransfer.dropEffect='move';
  if(Number(event.currentTarget.dataset.categoryId||0)!==dragCategoryId)event.currentTarget.classList.add('drop-target');
}
function dragLeaveCategory(event){event.currentTarget.classList.remove('drop-target');}
function dropCategory(event,targetId){
  if(!panelEditMode||dragCategoryId===null)return;event.preventDefault();event.currentTarget.classList.remove('drop-target');
  const sourceId=dragCategoryId;dragCategoryId=null;if(sourceId===targetId)return;
  const visibleIds=draftCategoryOrder.slice();const si=visibleIds.indexOf(sourceId),ti=visibleIds.indexOf(targetId);if(si<0||ti<0)return;
  visibleIds.splice(si,1);const rect=event.currentTarget.getBoundingClientRect();const after=event.clientX>rect.left+rect.width/2;visibleIds.splice(visibleIds.indexOf(targetId)+(after?1:0),0,sourceId);
  draftCategoryOrder=visibleIds;renderCategories();
}
function dragEndCategory(event){event.currentTarget.classList.remove('dragging','drop-target');document.querySelectorAll('.category.drop-target').forEach(el=>el.classList.remove('drop-target'));dragCategoryId=null;}

const tileSizeCycle=['mini','small','medium','wide','tall','large','xl','hero'];
function quickResizeApp(event,id){
  event.stopPropagation();if(!panelEditMode)return;const a=apps.find(x=>x.id===id);if(!a)return;
  const current=tileSizeCycle.indexOf(a.size);const next=tileSizeCycle[(current+1)%tileSizeCycle.length];a.size=next;draftAppChanges.set(id,{size:next});renderApps();
}
async function duplicateApp(event,id){
  event.stopPropagation();
  try{const r=await fetch(`/api/apps/${id}/duplicate`,{method:'POST'});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Не удалось дублировать приложение');await loadData();panelEditMode=true;draftAppOrder=apps.map(a=>a.id);draftCategoryOrder=categories.map(c=>c.id);updatePanelEditControls();renderCategories();renderApps();}
  catch(e){alert(e.message)}
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

function getTileAppearanceFromForm(){
  const mode=document.getElementById('tileBgMode')?.value||'default';
  let value='';
  if(mode==='color') value=document.getElementById('tileBgColor')?.value||'#191d27';
  if(mode==='image') value=document.getElementById('tileBgImage')?.value.trim()||'';
  return {
    tile_bg_mode:mode,
    tile_bg_value:value,
    tile_bg_scale:Math.round(clampNumber(document.getElementById('tileBgScale')?.value,50,200,100)),
    tile_opacity:clampNumber(document.getElementById('tileOpacity')?.value,45,100,90)/100,
    tile_blur:clampNumber(document.getElementById('tileBlur')?.value,0,20,6),
    tile_icon_size:Math.round(clampNumber(document.getElementById('tileIconSize')?.value,24,96,48)),
    tile_title_size:Math.round(clampNumber(document.getElementById('tileTitleSize')?.value,12,28,17)),
    tile_title_color:document.getElementById('tileTitleColor')?.value||'#ffffff',
    tile_description_color:document.getElementById('tileDescriptionColor')?.value||'#cbd5e1',
    tile_url_color:document.getElementById('tileUrlColor')?.value||'#94a3b8',
    tile_show_description:!!document.getElementById('tileShowDescription')?.checked,
    tile_show_url:!!document.getElementById('tileShowUrl')?.checked
  };
}

function setTileAppearanceForm(a={}){
  const mode=['default','color','image'].includes(a.tile_bg_mode)?a.tile_bg_mode:'default';
  const bgValue=String(a.tile_bg_value||'');
  const modeEl=document.getElementById('tileBgMode'); if(modeEl)modeEl.value=mode;
  const colorEl=document.getElementById('tileBgColor'); if(colorEl)colorEl.value=/^#[0-9a-f]{6}$/i.test(bgValue)?bgValue:'#191d27';
  const imageEl=document.getElementById('tileBgImage'); if(imageEl)imageEl.value=mode==='image'?bgValue:'';
  const setRange=(id,value)=>{const el=document.getElementById(id);if(el)el.value=String(value);};
  setRange('tileBgScale',Math.round(clampNumber(a.tile_bg_scale,50,200,100)));
  setRange('tileOpacity',Math.round(clampNumber(a.tile_opacity,0.45,1,0.90)*100));
  setRange('tileBlur',clampNumber(a.tile_blur,0,20,6));
  setRange('tileIconSize',Math.round(clampNumber(a.tile_icon_size,24,96,48)));
  setRange('tileTitleSize',Math.round(clampNumber(a.tile_title_size,12,28,17)));
  const setColor=(id,value,def)=>{const el=document.getElementById(id);if(el)el.value=/^#[0-9a-f]{6}$/i.test(String(value||''))?String(value):def;};
  setColor('tileTitleColor',a.tile_title_color,'#ffffff');
  setColor('tileDescriptionColor',a.tile_description_color,'#cbd5e1');
  setColor('tileUrlColor',a.tile_url_color,'#94a3b8');
  const desc=document.getElementById('tileShowDescription');if(desc)desc.checked=a.tile_show_description!==false;
  const showUrl=document.getElementById('tileShowUrl');if(showUrl)showUrl.checked=!!a.tile_show_url;
  updateTileAppearancePreview();
}

function applyLiveTileAppearancePreview(){
  const appId=Number(document.getElementById('appId')?.value||0);
  if(!appId)return;
  const card=document.querySelector(`.app-card[data-app-id="${appId}"]`);
  if(!card)return;

  const appearance=getTileAppearanceFromForm();
  const opacity=appearance.tile_opacity;
  const bgScale=appearance.tile_bg_scale;
  const blur=appearance.tile_blur;
  const iconSize=appearance.tile_icon_size;
  const titleSize=appearance.tile_title_size;
  const titleColor=appearance.tile_title_color||'#ffffff';
  const descriptionColor=appearance.tile_description_color||'#cbd5e1';
  const urlColor=appearance.tile_url_color||'#94a3b8';
  const mode=appearance.tile_bg_mode;
  const value=appearance.tile_bg_value;
  const rgb=getComputedStyle(document.documentElement).getPropertyValue('--card-rgb').trim()||'25,29,39';

  card.style.setProperty('--tile-bg-scale',String(bgScale/100));
  const bgLayer=card.querySelector(':scope > .tile-background-layer');
  if(bgLayer){ bgLayer.style.width=`${bgScale}%`; bgLayer.style.height=`${bgScale}%`; }
  card.style.setProperty('--tile-blur',`${blur}px`);
  card.style.setProperty('--tile-icon-size',`${iconSize}px`);
  card.style.setProperty('--tile-title-size',`${titleSize}px`);
  card.style.setProperty('--tile-title-color',safeCssColor(titleColor));
  card.style.setProperty('--tile-description-color',safeCssColor(descriptionColor));
  card.style.setProperty('--tile-url-color',safeCssColor(urlColor));

  if(mode==='image' && value){
    card.classList.add('tile-image-background');
    card.style.setProperty('--tile-bg-image',`url("${safeCssUrl(value)}")`);
    card.style.setProperty('--tile-bg-opacity',String(opacity));
    card.style.backgroundColor=`rgba(${rgb},1)`;
  }else{
    card.classList.remove('tile-image-background');
    card.style.setProperty('--tile-bg-image','none');
    card.style.setProperty('--tile-bg-opacity','1');
    if(mode==='color'){
      const colorRgb=hexToRgb(value)||rgb;
      card.style.backgroundColor=`rgba(${colorRgb},${opacity})`;
    }else{
      card.style.backgroundColor=`rgba(${rgb},${opacity})`;
    }
  }

  const icon=card.querySelector(':scope > .icon');
  const title=card.querySelector(':scope > .app-name');
  if(icon){
    icon.style.width=`${iconSize}px`;
    icon.style.height=`${iconSize}px`;
    icon.style.fontSize=`${Math.max(18,Math.round(iconSize*.52))}px`;
  }
  if(title)title.style.fontSize=`${titleSize}px`;
}

function updateTileAppearancePreview(){
  const mode=document.getElementById('tileBgMode')?.value||'default';
  document.getElementById('tileBgColorRow')?.classList.toggle('hidden',mode!=='color');
  document.getElementById('tileBgImageRow')?.classList.toggle('hidden',mode!=='image');
  document.getElementById('tileBgScaleRow')?.classList.toggle('hidden',mode!=='image');
  const opacity=clampNumber(document.getElementById('tileOpacity')?.value,45,100,90)/100;
  const bgScale=Math.round(clampNumber(document.getElementById('tileBgScale')?.value,50,200,100));
  const blur=clampNumber(document.getElementById('tileBlur')?.value,0,20,6);
  const iconSize=Math.round(clampNumber(document.getElementById('tileIconSize')?.value,24,96,48));
  const titleSize=Math.round(clampNumber(document.getElementById('tileTitleSize')?.value,12,28,17));
  const titleColor=document.getElementById('tileTitleColor')?.value||'#ffffff';
  const descriptionColor=document.getElementById('tileDescriptionColor')?.value||'#cbd5e1';
  const urlColor=document.getElementById('tileUrlColor')?.value||'#94a3b8';
  const color=document.getElementById('tileBgColor')?.value||'#191d27';
  const image=document.getElementById('tileBgImage')?.value.trim()||'';
  const preview=document.getElementById('tileStylePreview');
  if(preview){
    const rgb=mode==='color'?(hexToRgb(color)||'25,29,39'):(getComputedStyle(document.documentElement).getPropertyValue('--card-rgb').trim()||'25,29,39');
    preview.style.backgroundColor=`rgba(${rgb},${mode==='image'?1:opacity})`;
    preview.style.backdropFilter=`blur(${blur}px)`;
    preview.style.webkitBackdropFilter=`blur(${blur}px)`;
    preview.style.setProperty('--preview-bg-size',`${bgScale}%`);
    preview.style.setProperty('--preview-tile-blur',`${blur}px`);
    preview.style.setProperty('--preview-title-color',safeCssColor(titleColor));
    preview.style.setProperty('--preview-description-color',safeCssColor(descriptionColor));
    preview.style.setProperty('--preview-url-color',safeCssColor(urlColor));
    preview.style.setProperty('--preview-image-opacity',String(opacity));
    preview.style.setProperty('--preview-image', (mode==='image'&&image) ? `url("${safeCssUrl(image)}")` : 'none');
    preview.style.backgroundImage='none';
    preview.classList.toggle('preview-has-image',mode==='image'&&!!image);
    const icon=preview.querySelector('.preview-icon'); if(icon){icon.style.width=`${iconSize}px`;icon.style.height=`${iconSize}px`;icon.style.fontSize=`${Math.max(18,Math.round(iconSize*.52))}px`;}
    const title=preview.querySelector('.preview-title'); if(title)title.style.fontSize=`${titleSize}px`;
    const desc=preview.querySelector('.preview-description'); if(desc){desc.classList.toggle('hidden',!document.getElementById('tileShowDescription')?.checked); desc.textContent=document.getElementById('description')?.value.trim()||'Краткое описание приложения';}
    const url=preview.querySelector('.preview-url'); if(url){url.classList.toggle('hidden',!document.getElementById('tileShowUrl')?.checked); url.textContent=document.getElementById('url')?.value.trim()||'https://example.com';}
  }
  const valueEls={tileBgScaleValue:`${bgScale}%`,tileOpacityValue:`${Math.round(opacity*100)}%`,tileBlurValue:`${blur} px`,tileIconSizeValue:`${iconSize} px`,tileTitleSizeValue:`${titleSize} px`};
  for(const [id,value] of Object.entries(valueEls)){const el=document.getElementById(id);if(el)el.textContent=value;}
  applyLiveTileAppearancePreview();
}

async function persistTileAppearanceForExistingApp(){
  const id=Number(document.getElementById('appId')?.value||0);
  if(!id)return;
  const a=apps.find(x=>x.id===id);
  if(!a)return;
  const item={
    name:document.getElementById('name').value.trim(),
    url:document.getElementById('url').value.trim(),
    description:document.getElementById('description').value.trim(),
    category_id:Number(document.getElementById('categoryId').value),
    icon:document.getElementById('icon').value.trim()||'🚀',
    favorite:document.getElementById('favorite').checked,
    open_mode:document.getElementById('openMode').value==='embedded'?'embedded':'external',
    size:document.getElementById('tileSize').value,
    ...getTileAppearanceFromForm()
  };
  const r=await fetch(`/api/apps/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(item)});
  if(!r.ok){const data=await r.json().catch(()=>({}));throw new Error(data.detail||'Не удалось сохранить фон плитки');}
  const updated=await r.json();
  apps=apps.map(x=>x.id===id ? {...x,...updated} : x);
  renderApps();
}

async function uploadTileBackgroundFile(event){
  const file=event.target.files?.[0];event.target.value='';if(!file)return;
  try{
    const form=new FormData();form.append('file',file);
    const r=await fetch('/api/tile-background/upload',{method:'POST',body:form});
    const data=await r.json();if(!r.ok)throw new Error(data.detail||'Не удалось загрузить изображение');
    const mode=document.getElementById('tileBgMode');if(mode)mode.value='image';
    const input=document.getElementById('tileBgImage');if(input)input.value=data.url||'';
    updateTileAppearancePreview();
    await persistTileAppearanceForExistingApp();
  }catch(e){alert(e.message)}
}

async function importTileBackgroundFromUrl(){
  const input=document.getElementById('tileBgImage');const url=input?.value.trim();
  if(!url){alert('Укажите URL изображения');return}
  try{
    let data;
    if(url.startsWith('/backgrounds/')){
      data={url};
    }else{
      const r=await fetch('/api/tile-background/from-url',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
      data=await r.json();if(!r.ok)throw new Error(data.detail||'Не удалось скачать изображение');
    }
    input.value=data.url||url;
    const mode=document.getElementById('tileBgMode');if(mode)mode.value='image';
    updateTileAppearancePreview();
    await persistTileAppearanceForExistingApp();
  }catch(e){alert(e.message)}
}

function openAppModal(a=null){
  document.getElementById('modal').classList.remove('hidden');
  document.getElementById('modalTitle').textContent=a?'Изменить приложение':'Добавить приложение';
  document.getElementById('appId').value=a?.id||'';
  document.getElementById('name').value=a?.name||'';
  document.getElementById('url').value=a?.url||'';
  document.getElementById('openMode').value=a?.open_mode==='embedded'?'embedded':'external';
  document.getElementById('description').value=a?.description||'';
  document.getElementById('icon').value=a?.icon||'🚀';
  document.getElementById('appIconUrl').value='';
  renderIconChoices('appIconChoices','icon',appIcons);
  document.getElementById('favorite').checked=!!a?.favorite;
  document.getElementById('tileSize').value=['mini','small','medium','wide','tall','large','xl','hero'].includes(a?.size)?a.size:'medium';
  setTileAppearanceForm(a||{});
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
    open_mode:document.getElementById('openMode').value==='embedded'?'embedded':'external',
    size:document.getElementById('tileSize').value,
    ...getTileAppearanceFromForm()
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
    if(data.preferences?.theme)applyTheme(data.preferences.theme); else if(data.theme)applyTheme(data.theme);
    if(!confirm('Импортировать настройки? Текущие приложения и категории будут заменены данными из файла.')){event.target.value='';return}
    const r=await fetch('/api/settings/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result=await r.json();
    if(!r.ok)throw new Error(result.detail||'Ошибка импорта');
    selectedCategory='all';
    if(data.preferences?.theme==='light'||data.preferences?.theme==='dark'){ currentTheme=data.preferences.theme; localStorage.setItem('mdkdv-theme',currentTheme); applyTheme(currentTheme,false); }
    closeSettingsModal();
    await loadData();
    await loadBackgroundConfig();
    await loadAppearanceConfig();
    alert(`Настройки импортированы: ${result.categories} категорий, ${result.apps} приложений.`);
  }catch(e){alert(`Не удалось импортировать настройки: ${e.message}`)}finally{event.target.value=''}
}

function escapeHtml(v){return String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#039;')}
function escapeAttr(v){return escapeHtml(v)}

document.addEventListener('DOMContentLoaded',()=>{
  const searchField=document.getElementById('search');
  if(searchField){
    searchField.textContent='';
    searchField.addEventListener('input',renderApps);
    searchField.addEventListener('paste',()=>setTimeout(renderApps,0));
  }
  applyTheme(currentTheme,false);
  loadPreferences();
  const settingsButton=document.getElementById('settingsButton');
  if(settingsButton)settingsButton.addEventListener('click',openSettingsModal);
  const settingsModal=document.getElementById('settingsModal');
  if(settingsModal)settingsModal.addEventListener('click',event=>{if(event.target===settingsModal)closeSettingsModal()});
  const themeToggle=document.getElementById('themeToggle');
  if(themeToggle)themeToggle.addEventListener('click',toggleTheme);
  const themeSelect=document.getElementById('themeSelect');
  if(themeSelect)themeSelect.addEventListener('change',e=>applyTheme(e.target.value));
  const panelEditButton=document.getElementById('panelEditButton');
  if(panelEditButton)panelEditButton.addEventListener('click',()=>togglePanelEditMode());
  const panelEditCancel=document.getElementById('panelEditCancel');
  if(panelEditCancel)panelEditCancel.addEventListener('click',cancelPanelEditMode);
  const tileSize=document.getElementById('tileSize');
  if(tileSize)tileSize.addEventListener('change',updateTileSizePreview);
  ['tileBgMode','tileBgColor','tileBgImage','tileOpacity','tileBlur','tileIconSize','tileTitleSize','tileTitleColor','tileDescriptionColor','tileUrlColor','tileShowDescription','tileShowUrl'].forEach(id=>{
    const el=document.getElementById(id);
    if(el)el.addEventListener(el.type==='range'||el.type==='checkbox'||el.type==='color'?'input':'change',updateTileAppearancePreview);
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeSettingsModal();closeModal();closeCategoryModal()}});
  loadData().catch(e=>{console.error(e);document.getElementById('dashboard').innerHTML='<div class="empty">Ошибка загрузки Dashboard</div>'});
  loadBackgroundConfig();
  loadAppearanceConfig();
  startEmbyPolling();
});

// The Dashboard search is a contenteditable element rather than a form input.
// This prevents browser/password-manager credential autofill from treating it as a username field.
window.addEventListener('pageshow',()=>{
  const searchField=document.getElementById('search');
  if(searchField)searchField.textContent='';
});


document.addEventListener("keydown",handleEmbeddedEscape);
