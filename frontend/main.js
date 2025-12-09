let state = { plan_id: null, stu_id: null };

const $ = sel => document.querySelector(sel);
const $$ = sel => document.querySelectorAll(sel);

function toast(msg){
    const t = $('#toast');
    t.textContent = msg;
    t.classList.remove('hidden');
    setTimeout(()=>t.classList.add('hidden'), 1800);
}

// load state from localStorage
function hydrateState(){
    const sid = localStorage.getItem('stu_id');
    const pid = localStorage.getItem('plan_id');
    if (sid) state.stu_id = Number(sid);
    if (pid) state.plan_id = Number(pid);
}


// update when adding new tabs
function showTab(tab){
    ['#home', '#plan', '#history', '#schedule', '#final'].forEach(sel => {
        document.querySelector(sel)?.classList.add('hidden');
    });
    document.querySelector(tab)?.classList.remove('hidden');

    document.querySelectorAll('.nav a').forEach(a => {
        a.classList.remove('active');
    });
}



async function api(path, opts={}){
    const r = await fetch(path, opts);
    const j = await r.json().catch(()=>({}));
    if(!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
}

function renderRoute(){
    const p = location.pathname;
    let page = '#home';
    if (p === '/plan') page = '#plan';
    else if (p === '/history') page = '#history';
    else if (p === '/schedule') page = '#schedule';
    else if (p === '/final') page = '#final';
    
    showTab(page);
    document.querySelectorAll('.nav a').forEach(a => a.classList.remove('active'));
    if (page === '#home') document.getElementById('gotoHome')?.classList.add('active');
    if (page === '#plan') document.getElementById('gotoPlan')?.classList.add('active');
    if (page === '#history') document.getElementById('gotoHistory')?.classList.add('active');
    if (page === '#final') document.getElementById('gotoFinal')?.classList.add('active');

    // load data for the page
    if (page === '#plan' && state.stu_id && state.plan_id){
        Promise.all([loadPlan(), loadRecommendations(), loadSummary(), loadAdvisors()]);
    } else if (page === '#history' && state.stu_id){
        loadHistoryPage();
    }
    else if (page === '#schedule' && state.stu_id && state.plan_id){
    loadSchedulePage();
    } else if (page === '#final' && state.stu_id){
    loadFinalSchedule();
    }   

}
function routeTo(path){
    history.pushState({path}, '', path);
    renderRoute();
}

function renderProfile(stu){
    $('#profile').innerHTML =
        `<div><b>${stu.f_name} ${stu.l_name}</b> · ${stu.email}</div>
        <div>Advisor: ${stu.adv_first || ''} ${stu.adv_last || ''}</div>
        <div>Catalog Year: ${stu.catalog_year_id} · Expected Grad Term: ${stu.expected_grad_term}</div>`;
}

function onHistoryPage(){ return location.pathname === '/history'; }

function renderPlan(data){
    $('#plan_meta').textContent = `Plan ${state.plan_id} · Total credits ${data.total_credits || 0}`;
    const tbody = $('#plan_table tbody');
    tbody.innerHTML = '';
    if (!data.items || data.items.length === 0){
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="6" class="muted">No courses in this plan yet. Use search to add one.</td>`;
        tbody.appendChild(tr);
        return;
    }
    data.items.forEach(row=>{
        const tr = document.createElement('tr');
        tr.innerHTML =
        `<td>${row.recommended ? 'Yes' : 'No'}</td>
        <td>${row.term_code}</td>
        <td>${row.course_code || ''}</td>
        <td>${row.title || ''}</td>
        <td>${row.credits ?? ''}</td>
        <td><button class="ghost" data-pc="${row.pc_id}">Remove</button></td>`;
        tbody.appendChild(tr);
    });
    tbody.querySelectorAll('button[data-pc]').forEach(btn=>{
        btn.addEventListener('click', async ()=>{
        try{
            await api('/api/plan/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pc_id:Number(btn.dataset.pc)})});
            toast('Removed');
            await Promise.all([loadPlan(), loadRecommendations(), loadSummary(), onHistoryPage() ? loadHistoryPage() : Promise.resolve()]);
        }catch(e){ toast(e.message); }
        });
    });
}

function gradePoints(g){
  const m = {'A':4,'A-':3.7,'B+':3.3,'B':3,'B-':2.7,'C+':2.3,'C':2,'C-':1.7,'D':1,'F':0};
  return m[g] ?? null;
}
function standingFromCredits(c){
  if(c>=90) return 'Senior';
  if(c>=60) return 'Junior';
  if(c>=30) return 'Sophomore';
  return 'Freshman';
}

function dayName(n){
  const map = {1:'Mon', 2:'Tue', 3:'Wed', 4:'Thu', 5:'Fri', 6:'Sat', 7:'Sun'};
  return map[n] || n;
}

async function loadSummary(target = {credits:'#sum_credits', gpa:'#sum_gpa', standing:'#sum_standing'}){
  if(!state.stu_id) return;
  const j = await api(`/api/history?stu_id=${state.stu_id}`);
  let credits = 0, points = 0;
  j.items.forEach(it=>{
    const gp = gradePoints(String(it.grade||'').toUpperCase());
    const cr = Number(it.credits||0);
    if(gp !== null && cr > 0){
      credits += cr;
      points  += gp * cr;
    }
  });
  const gpa = credits ? (points / credits) : 0;
  document.querySelector(target.credits).textContent  = credits;
  document.querySelector(target.gpa).textContent      = gpa.toFixed(2);
  document.querySelector(target.standing).textContent = standingFromCredits(credits);
}



async function fetchPrograms(){
  const j = await api('/api/programs');
  const sel = $('#major_select');
  sel.innerHTML = '<option value="">Select your major</option>';
  j.items.forEach(p=>{
    const o = document.createElement('option');
    o.value = p.prog_id;
    o.textContent = `${p.name} (${p.program_type})`;
    sel.appendChild(o);
  });
}

async function loadCurrentMajor(){
  if(!state.stu_id) return;
  const j = await api(`/api/student/major?stu_id=${state.stu_id}`);
  const sel = $('#major_select');
  if(j.item){
    sel.value = j.item.prog_id;
  }
}

async function saveMajor(){
  const sel = $('#major_select');
  const prog_id = Number(sel.value);
  if(!state.stu_id || !prog_id){ toast('Pick a major'); return; }
  await api('/api/student/major',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({stu_id:state.stu_id, prog_id})
  });
  toast('Major saved');
  await loadRecommendations();
}

async function loadRecommendations(){
    if(!state.stu_id || !state.plan_id) return;
    const j = await api(`/api/recommendations?stu_id=${state.stu_id}&plan_id=${state.plan_id}`);
    const div = $('#rec_list');
    div.innerHTML = '';
    if(!j.items.length){
        div.innerHTML = `<div class="meta">No recommendations. You may have satisfied all core courses or need to mark more completed.</div>`;
        return;
    }
    // items ordered by semester standing
    j.items.forEach(it => {
        const row = document.createElement('div');
        row.innerHTML = `<div>
        <div><b>${it.subject} ${it.cata_num}</b> · ${it.title}</div>
        <div class="meta">id ${it.course_id} · ${it.credits} credits</div>
        </div>`;
        const add = document.createElement('button');
        add.textContent = 'Add to plan';
        add.addEventListener('click', async () => {
        try {
            await api('/api/plan/add_course', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                plan_id: state.plan_id,
                term_id: 8,
                course_id: it.course_id
            })
            });
            toast('Added');
            await Promise.all([loadPlan(), loadRecommendations(), loadSummary()]);
        } catch (e) {
            toast(e.message);
        }
        });
        row.appendChild(add);
        div.appendChild(row);
    });
}

async function fetchSubjects(){
    const j = await api('/api/subjects');
    const dl = document.querySelector('#subject_list');
    dl.innerHTML = '';
    j.items.forEach(s=>{
        const opt = document.createElement('option');
        opt.value = s; dl.appendChild(opt);
    });
    const sel = document.querySelector('#filter_subject');
    sel.innerHTML = '<option value="">Any subject</option>';
    j.items.forEach(s=>{
        const o = document.createElement('option');
        o.value = s; o.textContent = s; sel.appendChild(o);
    });
}

async function loadAdvisors(){
  const tableBody = document.querySelector('#advisor_table tbody');
  if (!tableBody) return;

  try {
    const j = await api('/api/advisors');
    const items = j.items || [];

    if (!items.length){
      tableBody.innerHTML = `
        <tr>
          <td colspan="2" class="muted">No advisors found.</td>
        </tr>`;
      return;
    }

    tableBody.innerHTML = '';
    items.forEach(a => {
      const tr = document.createElement('tr');
      const name = `${a.f_name} ${a.l_name}`;
      tr.innerHTML = `
        <td>${name}</td>
        <td><a href="mailto:${a.email}">${a.email}</a></td>
      `;
      tableBody.appendChild(tr);
    });
  } catch (e) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="2" class="muted">Error loading advisors.</td>
      </tr>`;
    toast(e.message);
  }
}

async function loadPlan(){
    if(!state.plan_id) return;
    const j = await api(`/api/plan?plan_id=${state.plan_id}`);
    renderPlan(j);
}
async function loadHistoryPage(){
    if(!state.stu_id) return;
    const j = await api(`/api/history?stu_id=${state.stu_id}`);
    const tbody = document.querySelector('#history_table tbody');
    tbody.innerHTML = '';
    if(!j.items.length){
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="5" class="muted">No completed courses recorded yet.</td>`;
        tbody.appendChild(tr);
    } else {
        j.items.forEach(h=>{
        const tr = document.createElement('tr');

        // grade select
        const sel = document.createElement('select');
        ['A','A-','B+','B','B-','C+','C','C-','D','F','P','NP'].forEach(g=>{
            const o = document.createElement('option'); o.value=g; o.textContent=g;
            if ((h.grade||'').toUpperCase() === g) o.selected = true;
            sel.appendChild(o);
        });
        const save = document.createElement('button');
        save.textContent = 'Save';
        save.addEventListener('click', async ()=>{
            try{
            await api('/api/history/update_grade', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({ stu_id: state.stu_id, enroll_id: h.enroll_id, grade: sel.value })
            });
            toast('Grade updated');
            await Promise.all([loadHistoryPage(), loadRecommendations(), loadSummary()]);
            }catch(e){ toast(e.message); }
        });
        const del = document.createElement('button');
        del.className = 'ghost';
        del.textContent = 'Remove';
        del.addEventListener('click', async ()=>{
            try{
            await api('/api/history/remove', {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({ stu_id: state.stu_id, enroll_id: h.enroll_id })
            });
            toast('Removed');
            await Promise.all([loadHistoryPage(), loadRecommendations(), loadSummary()]);
            }catch(e){ toast(e.message); }
        });

        tr.innerHTML = `<td>${h.term_code || ''}</td>
                        <td>${h.subject} ${h.cata_num}</td>
                        <td>${h.title}</td>
                        <td>${h.credits}</td>
                        <td>${h.grade || ''}</td>`;
        tr.children[4].appendChild(sel);
        tr.children[4].appendChild(save);
        tr.children[4].appendChild(del);
        tbody.appendChild(tr);
        });
  }
  await loadSummary({credits:'#sum_credits_hist', gpa:'#sum_gpa_hist', standing:'#sum_standing_hist'});
}

async function loadFinalSchedule(){
    if (!state.stu_id) return;

    const div = $('#final_schedule_content');
    if (!div) return;

    try {
        const j = await api(`/api/final_schedule?stu_id=${state.stu_id}`);
        const items = j.items || [];

        if (!items.length){
            div.innerHTML = `<div class="muted">No classes chosen yet.</div>`;
            return;
        }

        // Group meetings by section_id so each enrolled section is one row
        const sections = new Map();

        items.forEach(sec => {
            let entry = sections.get(sec.section_id);
            if (!entry) {
                entry = {
                    section_id: sec.section_id,
                    course_code: sec.course_code,
                    title: sec.title,
                    location: sec.location,
                    start_time: sec.start_time,
                    end_time: sec.end_time,
                    days: []
                };
                sections.set(sec.section_id, entry);
            }
            entry.days.push(dayName(sec.days_of_week));
        });

        const rowsHtml = Array.from(sections.values()).map(sec => {
            const start = sec.start_time ? String(sec.start_time).substring(0,5) : '';
            const end = sec.end_time ? String(sec.end_time).substring(0,5)   : '';
            const daysText = sec.days.join(', ');
            return `
                <tr>
                    <td>${sec.course_code}</td>
                    <td>${sec.title}</td>
                    <td>${daysText}</td>
                    <td>${start}–${end}</td>
                    <td>${sec.location || ''}</td>
                    <td><button class="ghost" data-sec="${sec.section_id}">Remove</button></td>
                </tr>
            `;
        }).join('');

        div.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Course</th>
                        <th>Title</th>
                        <th>Day(s)</th>
                        <th>Time</th>
                        <th>Location</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        `;

        div.querySelectorAll('button[data-sec]').forEach(btn => {
            btn.addEventListener('click', async () => {
                try {
                    await api('/api/final_schedule/remove', {
                        method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body: JSON.stringify({
                            stu_id: state.stu_id,
                            section_id: Number(btn.dataset.sec)
                        })
                    });
                    toast('Removed from schedule');
                    await loadFinalSchedule();
                } catch(e) {
                    toast(e.message);
                }
            });
        });

    } catch(e){
        div.innerHTML = `<div class="muted">Error loading final schedule: ${e.message}</div>`;
        toast(e.message);
    }
}

async function loadSchedulePage(){
    if (!state.plan_id) return;

    const div = $('#schedule_content');
    if (!div) return;

    div.innerHTML = '<div class="muted">Loading available class times...</div>';

    try {
        const j = await api(`/api/schedule?plan_id=${state.plan_id}`);
        const items = j.items || [];

        if (!items.length){
            div.innerHTML = `<div class="muted">No available schedule times found for your planned courses.</div>`;
            await loadFinalSchedule();
            return;
        }

        // Group meetings by section_id so each section is one row
        const sections = new Map();

        items.forEach(sec => {
            let entry = sections.get(sec.section_id);
            if (!entry) {
                entry = {
                    section_id: sec.section_id,
                    course_code: sec.course_code,
                    title: sec.title,
                    location: sec.location,
                    start_time: sec.start_time,
                    end_time: sec.end_time,
                    days: []
                };
                sections.set(sec.section_id, entry);
            }
            entry.days.push(dayName(sec.days_of_week));
        });

        const rowsHtml = Array.from(sections.values()).map(sec => {
            const start = sec.start_time ? String(sec.start_time).substring(0,5) : '';
            const end = sec.end_time ? String(sec.end_time).substring(0,5)   : '';
            const daysText = sec.days.join(', ');  
            return `
                <tr>
                    <td>${sec.course_code}</td>
                    <td>${sec.title}</td>
                    <td>${daysText}</td>
                    <td>${start}–${end}</td>
                    <td>${sec.location || ''}</td>
                    <td><button data-sec="${sec.section_id}">Choose</button></td>
                </tr>
            `;
        }).join('');

        div.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Course</th>
                        <th>Title</th>
                        <th>Day(s)</th>
                        <th>Time</th>
                        <th>Location</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        `;

        div.querySelectorAll('button[data-sec]').forEach(btn => {
            btn.addEventListener('click', async () => {
                try {
                    await api('/api/enroll', {
                        method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body: JSON.stringify({
                            stu_id: state.stu_id,
                            section_id: Number(btn.dataset.sec)
                        })
                    });
                    toast('Enrolled successfully!');
                    await loadFinalSchedule();
                } catch(e) {
                    toast(e.message);
                }
            });
        });

        await loadFinalSchedule();

    } catch(e){
        div.innerHTML = `<div class="muted">Error loading schedule: ${e.message}</div>`;
        toast(e.message);
        // still try to show final schedule
        await loadFinalSchedule();
    }
}


async function onSignin(){
    const login_id = $('#login_id').value.trim();
    if(!login_id){ toast('Enter login id'); return; }
    try{
        const j = await api(`/api/signin?login_id=${encodeURIComponent(login_id)}`);
        state.plan_id = j.plan_id;
        state.stu_id = j.student.stu_id;
        localStorage.setItem('stu_id', String(state.stu_id));
        localStorage.setItem('plan_id', String(state.plan_id));
        renderProfile(j.student);
        // if a major is selected save it as the primary major
        const majorSel = $('#major_select');
        const prog_id = majorSel && majorSel.value ? Number(majorSel.value) : 0;
        if (prog_id) {
            await api('/api/student/major', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ stu_id: state.stu_id, prog_id })
            });
        }
        await loadPlan();
        await loadCurrentMajor();
        await Promise.all([loadRecommendations(), loadSummary()]);
        routeTo('/plan');
        $('#gotoHome').classList.remove('active');
        $('#gotoPlan').classList.add('active');
    }catch(e){
        toast(e.message);
    }
}

async function onSearch(){
    const q = $('#search_q').value.trim();
    const subject = $('#filter_subject').value.trim();
    const level = $('#filter_level').value.trim();

    // if nothing provided, do nothing
    if(!q && !subject && !level){
        $('#search_results').innerHTML = '';
        toast('Enter a query or choose a filter');
        return;
    }

    try{
        const qs = new URLSearchParams();
        if(q) qs.set('q', q);
        if(subject) qs.set('subject', subject);
        if(level) qs.set('level', level);

        const j = await api(`/api/courses/search?${qs.toString()}`);
        const div = $('#search_results');
        div.innerHTML = '';
        j.items.forEach(it=>{
        const row = document.createElement('div');
        row.innerHTML = `<div>
            <div><b>${it.subject} ${it.cata_num}</b> · ${it.title}</div>
            <div class="meta">id ${it.course_id} · ${it.credits} credits</div>
            </div>`;
        const add = document.createElement('button');
        add.textContent = 'Add';
        add.addEventListener('click', async ()=>{
            try{
            await api('/api/plan/add_course',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({plan_id:state.plan_id, term_id:8, course_id:it.course_id})
            });
            toast('Added');
            // update plan and recommendations after adding a class
            await Promise.all([loadPlan(), loadRecommendations(), loadSummary()]);
            }catch(e){ toast(e.message); }
        });
        const gradeSel = document.createElement('select');
            ['A','A-','B+','B','B-','C+','C','C-','D','F'].forEach(g=>{
            const o = document.createElement('option'); o.value=g; o.textContent=g; gradeSel.appendChild(o);
        });
        const comp = document.createElement('button');
        comp.textContent = 'Mark completed';
        comp.addEventListener('click', async ()=>{
            try{
            await api('/api/history/add_course',{
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({stu_id:state.stu_id, course_id:it.course_id, grade:gradeSel.value})
            });
                toast('Recorded as completed');
                await Promise.all([loadRecommendations(), loadSummary(), onHistoryPage() ? loadHistoryPage() : Promise.resolve()]); 
            }catch(e){ toast(e.message); }
        });
        row.appendChild(add);
        row.appendChild(gradeSel);
        row.appendChild(comp);
        div.appendChild(row);
        });
    }catch(e){ toast(e.message); }
}



document.addEventListener('DOMContentLoaded', () => {
    hydrateState();

    $('#btn_signin')?.addEventListener('click', onSignin);
    $('#btn_search')?.addEventListener('click', onSearch);
    $('#btn_save_major')?.addEventListener('click', saveMajor);
    $('#btn_enroll')?.addEventListener('click', e => {
    e.preventDefault();
    routeTo('/schedule');
    });




    if ($('#major_select')) {
        fetchPrograms();
        fetchSubjects();
    }

    $('#gotoHome')?.addEventListener('click', e => {
        e.preventDefault();
        routeTo('/home');
    });

    $('#gotoPlan')?.addEventListener('click', e => {
        e.preventDefault();
        routeTo('/plan');
    });

    $('#gotoHistory')?.addEventListener('click', e => {
        e.preventDefault();
        routeTo('/history');
    });

    $('#gotoFinal')?.addEventListener('click', e => {
    e.preventDefault();
    routeTo('/final');
    });

    $('#search_q').addEventListener('keydown', (e)=>{
        if (e.key === 'Enter') { e.preventDefault(); onSearch(); }
    });

    window.addEventListener('popstate', renderRoute);

    renderRoute();
});




