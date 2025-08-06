// static/script.js (v5)

let allRegions = [];
let selectedRegions = [];
let configsList = [];
let currentTaskId = null;

window.addEventListener('DOMContentLoaded', () => {
  loadRegions();
  loadConfigs();
  setupDateDefaults();
  bindLogin();
  bindDownloadForm();
  bindFileRefresh();
  bindSlotButtons();
  loadASOSStations();
  loadAWSStations();
});

// 탭 전환
function showTab(tab) {
  document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
  document.querySelector(`.tab-button[data-tab="${tab}"]`).classList.add('active');
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById(`${tab}-tab`).classList.add('active');
  if (tab === 'files') loadFiles();
}

// 슬롯 버튼 바인딩
function bindSlotButtons() {
  document.querySelectorAll('.slot-button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.slot-button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.slot-content').forEach(c => c.classList.remove('active'));
      document.getElementById(`slot-${btn.dataset.slot}`).classList.add('active');
    });
  });
}

// 로그인 바인딩
function bindLogin() {
  document.getElementById('login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    try {
      const params = new URLSearchParams({ username, password });
      const res = await fetch('/api/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params
      });
      if (!res.ok) throw new Error('로그인 실패');
      const { access_token } = await res.json();
      localStorage.setItem('token', access_token);
      showTab('download');
    } catch (err) {
      alert(err.message);
    }
  });
}

// 단기예보 폼 바인딩
function bindDownloadForm() {
  document.getElementById('region-search').addEventListener('input', debounce(onSearch, 300));
  document.getElementById('download-form').addEventListener('submit', onSubmit);
}

// 파일 새로고침 바인딩
function bindFileRefresh() {
  document.getElementById('refresh-files').addEventListener('click', loadFiles);
}

// 날짜 기본값 설정 (단기예보)
function setupDateDefaults() {
  const today = new Date();
  const lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate());
  document.getElementById('start_date').value = lastMonth.toISOString().split('T')[0];
  document.getElementById('end_date').value   = today.toISOString().split('T')[0];
}

// 지역 목록 로드
async function loadRegions() {
  try {
    const res = await fetch('/api/regions');
    const { regions } = await res.json();
    allRegions = regions;
    renderRegionList(regions);
  } catch (e) {
    console.error('지역 목록 로드 실패:', e);
  }
}

// 설정 목록 로드
async function loadConfigs() {
  try {
    const res = await fetch('/api/configs');
    const { configs } = await res.json();
    configsList = configs;
    const sel = document.getElementById('config-select');
    configs.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.name;
      opt.textContent = `${c.name} - ${c.description}`;
      sel.appendChild(opt);
    });
    sel.addEventListener('change', e => renderVariables(e.target.value));
  } catch (e) {
    console.error('설정 목록 로드 실패:', e);
  }
}

// ASOS 관측소 목록 로드 & 다운로드 핸들러
async function loadASOSStations() {
  try {
    const res = await fetch('/api/asos/stations');
    if (!res.ok) {
      console.error('ASOS stations API not found:', res.status, res.statusText);
      return;
    }
    const { stations } = await res.json();
    const sel = document.getElementById('asos-region');
    sel.innerHTML = '';
    stations.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.code;
      opt.textContent = s.name;
      sel.appendChild(opt);
    });

    document.getElementById('asos-form').addEventListener('submit', async e => {
      e.preventDefault();

      // 1) API 키 읽기
      const serviceKey = document.getElementById('asos-service-key').value.trim();
      if (!serviceKey) {
        alert('API 키를 입력해주세요.');
        return;
      }

      // 2) 날짜 파싱 & 포맷 변경
      const startInput = document.getElementById('asos-start-date').value;
      const endInput   = document.getElementById('asos-end-date').value;
      if (!startInput || !endInput) {
        alert('시작일과 종료일을 모두 선택해주세요.');
        return;
      }
      const start = startInput.replace(/-/g, '');
      const end   = endInput.replace(/-/g, '');

      // 3) 선택된 관측소 코드 수집
      const regionCodes = Array.from(
        document.getElementById('asos-region').selectedOptions
      ).map(o => o.value);
      if (!regionCodes.length) {
        alert('적어도 하나의 지역을 선택해주세요.');
        return;
      }

      // 4) Progress UI 초기화
      const progressEl = document.getElementById('download-progress');
      const statusEl   = document.getElementById('download-status');
      const total      = regionCodes.length;
      let completed    = 0;
      progressEl.max   = total;
      progressEl.value = 0;
      progressEl.style.display = 'block';
      statusEl.textContent = `0 / ${total} 다운로드 시작…`;

      // 5) 순차 다운로드
      for (const code of regionCodes) {
        statusEl.textContent = `${completed} / ${total} 다운로드 중: 코드 ${code}`;

        // URLSearchParams에 FastAPI가 기대하는 alias명 사용
        const params = new URLSearchParams({
          service_key: encodeURIComponent(serviceKey),
          start:       encodeURIComponent(start),
          end:         encodeURIComponent(end),
          stnIds:      encodeURIComponent(code),
        }).toString();

        let resp;
        try {
          resp = await fetch(`/api/download/asos?${params}`);
        } catch (networkErr) {
          console.error(networkErr);
          alert(`[코드 ${code}] 네트워크 오류가 발생했습니다.`);
          continue;
        }

        if (!resp.ok) {
          let errText = `${resp.status} ${resp.statusText}`;
          try {
            const js = await resp.json();
            errText = js.detail || errText;
          } catch {
            errText = await resp.text();
          }
          alert(`[코드 ${code}] ${errText}`);
        } else {
          const blob = await resp.blob();
          const filename = `ASOS_${code}_${start}_${end}.csv`;
          const link = document.createElement('a');
          link.href = URL.createObjectURL(blob);
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }

        // 진행률 업데이트
        completed += 1;
        progressEl.value = completed;
        statusEl.textContent = `${completed} / ${total} 완료`;
      }

      // 6) 완료 후 UI 정리
      statusEl.textContent = `모든 다운로드 완료 (${total} / ${total})`;
      setTimeout(() => {
        progressEl.style.display = 'none';
        statusEl.textContent = '';
      }, 2000);
    });
  } catch (e) {
    console.error('ASOS stations load failed:', e);
  }
}



// 검색어 필터링
function onSearch(e) {
  const term = e.target.value.trim().toLowerCase();
  const filtered = term
    ? allRegions.filter(r =>
        r.level1.toLowerCase().includes(term) ||
        r.level2.toLowerCase().includes(term) ||
        r.level3.toLowerCase().includes(term)
      )
    : allRegions;
  renderRegionList(filtered);
}

// 지역 리스트 렌더링
function renderRegionList(list) {
  const cont = document.getElementById('region-list');
  cont.innerHTML = '';
  if (!list.length) {
    cont.innerHTML = '<p style="padding:10px">검색 결과가 없습니다.</p>';
    return;
  }
  list.forEach(r => {
    const d = document.createElement('div');
    d.className = 'region-item';
    d.textContent = `${r.level1} / ${r.level2} / ${r.level3}`;
    d.onclick = () => selectRegion(r);
    cont.appendChild(d);
  });
}

// 지역 선택
function selectRegion(r) {
  if (selectedRegions.find(x => x.code === r.code)) {
    return alert('이미 선택된 지역입니다.');
  }
  selectedRegions.push(r);
  renderSelectedRegions();
}

// 선택된 지역 표시
function renderSelectedRegions() {
  const cont = document.getElementById('selected-regions');
  cont.querySelectorAll('.selected-region').forEach(el => el.remove());
  selectedRegions.forEach((r, i) => {
    const d = document.createElement('div');
    d.className = 'selected-region';
    d.innerHTML = `
      <span>${r.level1} / ${r.level2} / ${r.level3}</span>
      <button class="remove-btn" onclick="removeRegion(${i})">×</button>
    `;
    cont.appendChild(d);
  });
}

// 선택 해제
function removeRegion(i) {
  selectedRegions.splice(i, 1);
  renderSelectedRegions();
}

// 변수 체크박스 렌더링
function renderVariables(name) {
  const cont = document.getElementById('variables-container');
  cont.innerHTML = '';
  const cfg = configsList.find(c => c.name === name);
  if (!cfg) return;
  cfg.variables.forEach(v => {
    const label = document.createElement('label');
    label.className = 'variable-item';
    label.innerHTML = `<input type="checkbox" value="${v.code}" /> ${v.name}`;
    cont.appendChild(label);
  });
}

// 단기예보 폼 제출
async function onSubmit(e) {
  e.preventDefault();
  if (!selectedRegions.length) return alert('지역을 선택해주세요.');
  const configName = document.getElementById('config-select').value;
  if (!configName) return alert('예보 유형을 선택해주세요.');
  const checked = Array.from(document.querySelectorAll('#variables-container input:checked')).map(i => i.value);
  const cfg = configsList.find(c => c.name === configName);
  const vars = cfg.variables.filter(v => checked.includes(v.code));
  if (!vars.length) return alert('변수를 선택해주세요.');

  const form = new FormData(e.target);
  form.set('regions', JSON.stringify(selectedRegions));
  form.set('variables', JSON.stringify(vars));

  const token = localStorage.getItem('token');
  if (!token) return alert('먼저 로그인해 주세요!');

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: form
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.detail || '다운로드 요청 실패');
    currentTaskId = json.task_id;
    showProgress();
    pollStatus();
  } catch (err) {
    alert('다운ロード 오류: ' + err.message);
  }
}

// 진행바 표시
function showProgress() {
  document.getElementById('download-form').style.display      = 'none';
  document.getElementById('progress-container').style.display = 'block';
}
function hideProgress() {
  document.getElementById('download-form').style.display      = 'block';
  document.getElementById('progress-container').style.display = 'none';
}

// 상태 폴링
function pollStatus() {
  const interval = setInterval(async () => {
    try {
      const res = await fetch(`/api/status/${currentTaskId}`);
      const status = await res.json();
      const pct = status.total ? ((status.progress / status.total) * 100).toFixed(1) : 0;
      document.getElementById('progress-fill').style.width    = pct + '%';
      document.getElementById('progress-text').textContent    = `${status.progress}/${status.total} (${pct}%)`;
      document.getElementById('progress-details').textContent = `현재: ${status.current_item}`;
      if (status.status === 'completed' || status.status === 'error') {
        clearInterval(interval);
        if (status.status === 'completed') showToast('다운로드가 완료되었습니다!');
        else alert('다운ロード 중 오류: ' + status.error);
        hideProgress();
      }
    } catch (e) {
      console.error('상태 조회 실패:', e);
      clearInterval(interval);
      hideProgress();
    }
  }, 1000);
}

// 파일 목록 로드
async function loadFiles() {
  const container = document.getElementById('files-list');
  container.innerHTML = '<p>로딩 중...</p>';
  try {
    const res = await fetch('/api/files');
    const { files } = await res.json();
    if (!files.length) {
      container.innerHTML = '<p>다운로드된 파일이 없습니다。</p>';
      return;
    }
    container.innerHTML = '';
    files.forEach(f => {
      const div = document.createElement('div');
      div.className = 'file-item';
      div.innerHTML = `
        <div class="file-info">
          <strong>${f.name}</strong>
          <p>크기: ${formatFileSize(f.size)} | 수정: ${new Date(f.modified).toLocaleString()}</p>
        </div>
        <div class="file-actions">
          <button class="btn-small btn-download" onclick="downloadFile('${f.path}')">
            <i class="fas fa-download"></i> 다운로드
          </button>
        </div>`;
      container.appendChild(div);
    });
  } catch (e) {
    console.error('파일 목록 로드 실패:', e);
    container.innerHTML = '<p>파일 목록을 불러오는 중 오류가 발생했습니다。</p>';
  }
}

// 파일 다운로드 헬퍼
function downloadFile(path) {
  const url = `${window.location.origin}/api/download-file/${encodeURIComponent(path).replace(/%2F/g,'/')}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// 파일 크기 포맷
function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024, sizes = ['Bytes','KB','MB','GB'];
  const i = Math.floor(Math.log(bytes)/Math.log(k));
  return (bytes/Math.pow(k,i)).toFixed(2)+' '+sizes[i];
}

// 디바운스
function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

// 토스트 메시지
function showToast(msg, dur = 3000) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), dur);
}