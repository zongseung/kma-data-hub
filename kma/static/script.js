// static/script.js

let allRegions = [],
    selectedRegions = [],
    configsList = [],
    currentTaskId = null;    // ← 여기에 task_id 저장

// 탭 전환
function showTab(tab) {
  document.querySelectorAll(".tab-button").forEach(b => b.classList.remove("active"));
  document.querySelector(`.tab-button[data-tab="${tab}"]`).classList.add("active");
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
  document.getElementById(`${tab}-tab`).classList.add("active");

  if (tab === "files") {
    loadFiles();
  }
}

// 초기화
document.addEventListener("DOMContentLoaded", () => {
  loadRegions();
  loadConfigs();
  setupDateDefaults();

  document.getElementById("region-search")
    .addEventListener("input", debounce(onSearch, 300));

  document.getElementById("download-form")
    .addEventListener("submit", onSubmit);

  document.getElementById("refresh-files")
    .addEventListener("click", () => loadFiles());
});

// 1) regions 가져오기
async function loadRegions() {
  try {
    const res = await fetch("/api/regions");
    const { regions } = await res.json();
    allRegions = regions;
    renderRegionList(allRegions);
  } catch (e) {
    console.error("지역 목록 로드 실패:", e);
  }
}

// 2) configs 가져오기
async function loadConfigs() {
  try {
    const res = await fetch("/api/configs");
    const { configs } = await res.json();
    configsList = configs;
    const sel = document.getElementById("config-select");
    configs.forEach(c => {
      let opt = document.createElement("option");
      opt.value = c.name;
      opt.textContent = `${c.name} - ${c.description}`;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", e => renderVariables(e.target.value));
  } catch (e) {
    console.error("설정 목록 로드 실패:", e);
  }
}

// 3) 날짜 기본값
function setupDateDefaults() {
  const today = new Date(),
        lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate());
  document.getElementById("start_date").value = lastMonth.toISOString().split("T")[0];
  document.getElementById("end_date").value   = today.toISOString().split("T")[0];
}

// 4) 검색어 변경
function onSearch(e) {
  const term = e.target.value.trim().toLowerCase();
  renderRegionList(term
    ? allRegions.filter(r =>
        r.level1.toLowerCase().includes(term) ||
        r.level2.toLowerCase().includes(term) ||
        r.level3.toLowerCase().includes(term)
      )
    : allRegions
  );
}

// 5) 좌측 리스트 렌더링
function renderRegionList(list) {
  const cont = document.getElementById("region-list");
  cont.innerHTML = "";
  if (!list.length) {
    cont.innerHTML = `<p style="padding:10px">검색 결과가 없습니다.</p>`;
    return;
  }
  list.forEach(r => {
    let d = document.createElement("div");
    d.className = "region-item";
    d.textContent = `${r.level1} / ${r.level2} / ${r.level3}`;
    d.onclick = () => selectRegion(r);
    cont.appendChild(d);
  });
}

// 6) 지역 선택
function selectRegion(r) {
  if (selectedRegions.find(x => x.code === r.code)) {
    return alert("이미 선택된 지역입니다.");
  }
  selectedRegions.push(r);
  renderSelectedRegions();
}

// 7) 우측 선택된 지역 렌더링
function renderSelectedRegions() {
  const cont = document.getElementById("selected-regions");
  cont.querySelectorAll(".selected-region").forEach(el => el.remove());
  selectedRegions.forEach((r, i) => {
    let d = document.createElement("div");
    d.className = "selected-region";
    d.innerHTML = `
      <span>${r.level1} / ${r.level2} / ${r.level3}</span>
      <button class="remove-btn" onclick="removeRegion(${i})">×</button>
    `;
    cont.appendChild(d);
  });
}

// 8) 선택 해제
function removeRegion(i) {
  selectedRegions.splice(i, 1);
  renderSelectedRegions();
}

// 9) 변수 렌더링
function renderVariables(name) {
  const cont = document.getElementById("variables-container");
  cont.innerHTML = "";
  const cfg = configsList.find(c => c.name === name);
  if (!cfg) return;
  cfg.variables.forEach(v => {
    let label = document.createElement("label");
    label.className = "variable-item";
    label.innerHTML = `<input type="checkbox" value="${v.code}" /> ${v.name}`;
    cont.appendChild(label);
  });
}

// 10) 폼 제출
async function onSubmit(e) {
  e.preventDefault();

  if (!selectedRegions.length) return alert("지역을 선택해주세요.");
  const configName = document.getElementById("config-select").value;
  if (!configName) return alert("예보 유형을 선택해주세요.");

  const checked = Array.from(document.querySelectorAll("#variables-container input:checked"))
                       .map(i => i.value);
  const cfg = configsList.find(c => c.name === configName);
  const vars = cfg.variables.filter(v => checked.includes(v.code));
  if (!vars.length) return alert("변수를 선택해주세요.");

  const form = new FormData(e.target);
  form.set("regions",   JSON.stringify(selectedRegions));
  form.set("variables", JSON.stringify(vars));

  try {
    const res = await fetch("/api/download", { method: "POST", body: form });
    const j   = await res.json();
    if (!res.ok) throw new Error(j.detail || "다운로드 요청 실패");

    // — 다운로드 시작 UI —
    currentTaskId = j.task_id;
    showProgress();
    pollStatus();
  } catch (err) {
    alert("다운로드 오류: " + err.message);
  }
}

// 진행바 보이기/숨기기
function showProgress() {
  document.getElementById("download-form").style.display      = "none";
  document.getElementById("progress-container").style.display = "block";
}
function hideProgress() {
  document.getElementById("download-form").style.display      = "block";
  document.getElementById("progress-container").style.display = "none";
}

// 상태 폴링
function pollStatus() {
  const interval = setInterval(async () => {
    try {
      const res    = await fetch(`/api/status/${currentTaskId}`);
      const status = await res.json();

      const pct = status.total
        ? ((status.progress / status.total) * 100).toFixed(1)
        : 0;

      document.getElementById("progress-fill").style.width    = pct + "%";
      document.getElementById("progress-text").textContent    =
        `${status.progress}/${status.total} (${pct}%)`;
      document.getElementById("progress-details").textContent =
        `현재: ${status.current_item}`;

      if (status.status === "completed" || status.status === "error") {
        clearInterval(interval);
        if (status.status === "completed") {
          alert("다운로드가 완료되었습니다!");
        } else {
          alert("다운로드 중 오류: " + status.error);
        }
        hideProgress();
      }
    } catch (e) {
      console.error("상태 조회 실패:", e);
      clearInterval(interval);
      hideProgress();
    }
  }, 1000);
}

// ——————————————
// 11) 파일 관리: 목록 불러오기
// ——————————————
async function loadFiles() {
  const container = document.getElementById("files-list");
  container.innerHTML = "<p>로딩 중...</p>";

  try {
    const res = await fetch("/api/files");
    const { files } = await res.json();

    if (!files.length) {
      container.innerHTML = "<p>다운로드된 파일이 없습니다.</p>";
      return;
    }

    container.innerHTML = "";
    files.forEach(f => {
      const div = document.createElement("div");
      div.className = "file-item";
      div.innerHTML = `
        <div class="file-info">
          <strong>${f.name}</strong>
          <p>크기: ${formatFileSize(f.size)} | 수정: ${new Date(f.modified).toLocaleString()}</p>
        </div>
        <div class="file-actions">
          <button class="btn-small btn-download" onclick="downloadFile('${f.path}')">
            <i class="fas fa-download"></i> 다운로드
          </button>
        </div>
      `;
      container.appendChild(div);
    });
  } catch (e) {
    console.error("파일 목록 로드 실패:", e);
    container.innerHTML = "<p>파일 목록을 불러오는 중 오류가 발생했습니다.</p>";
  }
}

function downloadFile(path) {
  /* 1) 전체 경로를 encodeURIComponent
       2) %2F → / (슬래시는 복구) */
  const encoded = encodeURIComponent(path).replace(/%2F/g, "/");

  // a 태그로 강제 다운로드
  const a = document.createElement("a");
  a.href = `/api/download-file/${encoded}`;
  a.download = "";        // 브라우저에 “저장” 강제
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// 13) 바이트 → 읽기 좋은 문자열
function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024, sizes = ["Bytes","KB","MB","GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return (bytes / Math.pow(k, i)).toFixed(2) + " " + sizes[i];
}

// 디바운스 유틸 (원본 그대로)
function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms) };
}

// ——————————————
// 11) 파일 관리: 목록 불러오기
// ——————————————
// loadFiles() 교체 예시
async function loadFiles(){
  const box = document.getElementById("files-list");
  box.innerHTML = "<p class='files-empty'>로딩 중...</p>";

  try{
    const res = await fetch("/api/files");
    const { files } = await res.json();

    if(!files.length){
      box.innerHTML = "<p class='files-empty'>다운로드된 파일이 없습니다.</p>";
      return;
    }

    box.innerHTML = "";
    files.forEach(f=>{
      const card = document.createElement("div");
      card.className = "file-card";
      card.innerHTML = `
        <div>
          <div class="file-head">
            <i class="fas fa-file-csv"></i>
            <strong>${f.name}</strong>
          </div>
          <div class="file-meta">
            크기 : ${formatFileSize(f.size)}<br>
            수정 : ${new Date(f.modified).toLocaleString()}
          </div>
        </div>
        <button class="btn-download" onclick="downloadFile('${encodeURI(f.path)}')">
          <i class="fas fa-download"></i> 다운로드
        </button>
      `;
      box.appendChild(card);
    });
  }catch(e){
    console.error("파일 목록 로드 실패:",e);
    box.innerHTML = "<p class='files-empty'>목록을 불러오는 중 오류가 발생했습니다.</p>";
  }
}

// 13) 바이트 → 읽기 좋은 문자열
function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024, sizes = ["Bytes","KB","MB","GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return (bytes / Math.pow(k, i)).toFixed(2) + " " + sizes[i];
}
