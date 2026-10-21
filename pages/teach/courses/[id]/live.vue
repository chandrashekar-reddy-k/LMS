<script setup lang="ts">
import { Plus, Video, ExternalLink, Users, Pencil, Ban, Trash2, PlayCircle, Radio, Download, AlertTriangle, Mail, Check, Minus } from 'lucide-vue-next'

useSeoMeta({ title: 'Live classes - Infohive' })
definePageMeta({ middleware: 'staff', layout: 'dashboard' })

const route = useRoute()
const api = useApi()
const { show } = useToast()
const courseId = Number(route.params.id)

const data = ref<{ enrolled: number; sessions: any[] }>({ enrolled: 0, sessions: [] })
const loading = ref(true)
const load = async () => {
  loading.value = true
  try { data.value = await api.get<any>(`/teach/courses/${courseId}/live`) } finally { loading.value = false }
}
onMounted(load)

// ---------- schedule / edit ----------
const pad = (n: number) => String(n).padStart(2, '0')
const toLocalInput = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
const nextHour = () => { const d = new Date(); d.setHours(d.getHours() + 1, 0, 0, 0); return d }

const modal = ref<{ open: boolean; editing?: any }>({ open: false })
const form = ref<any>({})
const saving = ref(false)
const openForm = (s?: any) => {
  modal.value = { open: true, editing: s }
  form.value = s
    ? { title: s.title, description: s.description || '', starts_local: toLocalInput(new Date(s.starts_at)), duration_minutes: s.duration_minutes,
        provider: s.provider, external_url: s.external_url || '', recording_url: s.recording_url || '' }
    : { title: '', description: '', starts_local: toLocalInput(nextHour()), duration_minutes: 60, provider: 'jitsi', external_url: '', recording_url: '' }
}
const tz = Intl.DateTimeFormat().resolvedOptions().timeZone

const save = async () => {
  const f = form.value
  if (f.title.trim().length < 2) return show('Give the class a title', 'error')
  const starts = new Date(f.starts_local)
  if (isNaN(starts.getTime())) return show('Pick a date and time', 'error')
  if (f.provider === 'external' && !/^https:\/\//i.test(f.external_url)) return show('Paste the https:// meeting link', 'error')
  const body: any = {
    title: f.title.trim(), description: f.description || null, starts_at: starts.toISOString(),
    duration_minutes: Number(f.duration_minutes) || 60, provider: f.provider,
    external_url: f.provider === 'external' ? f.external_url.trim() : null,
  }
  saving.value = true
  try {
    if (modal.value.editing) {
      body.recording_url = f.recording_url.trim() || null
      await api.put(`/teach/live/${modal.value.editing.id}`, body)
      show('Live class updated')
    } else {
      await api.post(`/teach/courses/${courseId}/live`, body)
      show('Live class scheduled - enrolled students have been notified')
    }
    modal.value = { open: false }
    await load()
  } catch { /* toast shown */ } finally { saving.value = false }
}

const cancelSession = async (s: any) => {
  if (!confirm(`Cancel "${s.title}"? Enrolled students will be notified.`)) return
  await api.post(`/teach/live/${s.id}/cancel`)
  show('Live class cancelled', 'info')
  await load()
}
const removeSession = async (s: any) => {
  if (!confirm(`Delete "${s.title}" and its attendance record?`)) return
  await api.del(`/teach/live/${s.id}`)
  show('Deleted', 'info')
  await load()
}

// ---------- attendance ----------
const att = ref<any>(null)
const openAttendance = async (s: any) => { att.value = await api.get<any>(`/teach/live/${s.id}/attendance`) }
const dateTime = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
// while a class is running, "Absent" would be premature
const absentLabel = computed(() => att.value?.session.state === 'live' ? 'Not joined yet' : 'Absent')
const exportSession = () => {
  const a = att.value
  if (!a) return
  downloadCsv(`attendance-${fileSlug(a.session.title)}-${a.session.starts_at.slice(0, 10)}.csv`, [
    ['Class', a.session.title], ['Date', dateTime(a.session.starts_at)], ['Present', `${a.present} of ${a.total}`], [],
    ['Learner', 'Email', 'Status', 'First joined', 'Times joined'],
    ...a.rows.map((r: any) => [r.user.full_name, r.user.email, r.present ? 'Present' : absentLabel.value,
      r.first_joined_at ? dateTime(r.first_joined_at) : '', r.join_count]),
  ])
}

// ---------- course-wide register ----------
const tab = ref<'classes' | 'register'>(route.query.tab === 'register' ? 'register' : 'classes')
const reg = ref<any>(null)
const regLoading = ref(false)
const onlyAtRisk = ref(false)
const loadRegister = async () => {
  regLoading.value = true
  try { reg.value = await api.get<any>(`/teach/courses/${courseId}/attendance`) } finally { regLoading.value = false }
}
watch(tab, (t) => { if (t === 'register' && !reg.value) loadRegister() }, { immediate: true })
const regRows = computed(() => (reg.value?.learners || []).filter((r: any) => !onlyAtRisk.value || r.at_risk))
const shortDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
const riskReason = (r: any) => r.missed_in_a_row >= reg.value.thresholds.missed_in_a_row
  ? `Missed the last ${r.missed_in_a_row} classes` : `Below ${reg.value.thresholds.rate}% attendance`
const rateClass = (rate: number | null) => rate === null ? 'bg-slate-200' : rate >= 80 ? 'bg-brand-500' : rate >= 60 ? 'bg-amber-400' : 'bg-rose-500'
const exportRegister = () => {
  const r = reg.value
  if (!r) return
  downloadCsv(`attendance-register-${fileSlug(r.course.title)}.csv`, [
    ['Learner', 'Email', 'Attended', 'Classes since enrolling', 'Attendance %', 'Missed in a row', 'Needs attention',
      ...r.sessions.map((s: any) => `${s.title} (${shortDate(s.starts_at)})`)],
    ...r.learners.map((l: any) => [l.user.full_name, l.user.email, l.present, l.eligible, l.rate ?? '', l.missed_in_a_row,
      l.at_risk ? 'Yes' : 'No',
      ...l.cells.map((c: any) => c.status === 'present' ? 'Present' : c.status === 'absent' ? 'Absent' : 'Not enrolled yet')]),
  ])
}

const when = (iso: string) => new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
const stateBadge: Record<string, [string, string]> = {
  live: ['Live now', 'bg-rose-50 text-rose-700'], starting_soon: ['Starting soon', 'bg-amber-50 text-amber-700'],
  upcoming: ['Scheduled', 'bg-sky-50 text-sky-700'], ended: ['Ended', 'bg-slate-100 text-slate-500'],
  cancelled: ['Cancelled', 'bg-slate-100 text-slate-400'],
}
</script>

<template>
  <div :class="tab === 'register' ? 'max-w-6xl' : 'max-w-4xl'">
    <div class="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div>
        <h1 class="text-2xl font-extrabold text-slate-900">Live classes</h1>
        <p class="text-slate-500 text-sm mt-0.5">Schedule live sessions. Enrolled students are notified by email and in the app, and can join 15 minutes early.</p>
      </div>
      <button class="btn-primary" @click="openForm()"><Plus class="w-4 h-4" /> Schedule a class</button>
    </div>

    <div role="tablist" aria-label="Live classes view" class="flex gap-1 border-b border-slate-200 mb-5">
      <button v-for="t in [{ k: 'classes', l: 'Classes' }, { k: 'register', l: 'Attendance register' }]" :key="t.k" type="button" role="tab"
        :aria-selected="tab === t.k" class="px-3.5 py-2.5 text-sm font-semibold border-b-2 -mb-px transition"
        :class="tab === t.k ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-600 hover:text-slate-900'" @click="tab = t.k as any">
        {{ t.l }}<span v-if="t.k === 'register' && reg?.at_risk_count" class="ml-1.5 badge bg-amber-100 text-amber-800">{{ reg.at_risk_count }}</span>
      </button>
    </div>

    <!-- REGISTER -->
    <template v-if="tab === 'register'">
      <div v-if="regLoading && !reg" class="card h-48 animate-pulse" />
      <div v-else-if="reg && !reg.sessions.length" class="card p-10 text-center text-slate-600">
        <Users class="w-10 h-10 mx-auto mb-2 text-slate-300" />
        No classes have taken place yet. The register fills in once your first live class starts.
      </div>
      <template v-else-if="reg">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <div class="card p-4"><div class="text-xs font-semibold text-slate-600">Average attendance</div><div class="text-2xl font-extrabold text-slate-900 mt-1">{{ reg.overall_rate ?? '-' }}<span v-if="reg.overall_rate !== null" class="text-base">%</span></div></div>
          <div class="card p-4"><div class="text-xs font-semibold text-slate-600">Classes held</div><div class="text-2xl font-extrabold text-slate-900 mt-1">{{ reg.sessions.length }}</div></div>
          <div class="card p-4"><div class="text-xs font-semibold text-slate-600">Learners</div><div class="text-2xl font-extrabold text-slate-900 mt-1">{{ reg.learners.length }}</div></div>
          <div class="card p-4"><div class="text-xs font-semibold text-slate-600">Need attention</div><div class="text-2xl font-extrabold mt-1" :class="reg.at_risk_count ? 'text-amber-700' : 'text-slate-900'">{{ reg.at_risk_count }}</div></div>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
          <label class="flex items-center gap-2 text-sm text-slate-700">
            <input v-model="onlyAtRisk" type="checkbox" class="rounded border-slate-300 text-brand-600" />
            Only learners who need attention
          </label>
          <button class="btn-secondary" @click="exportRegister"><Download class="w-4 h-4" /> Export CSV</button>
        </div>

        <div class="card overflow-x-auto relative">
          <table class="table-base">
            <thead>
              <tr>
                <th class="sticky left-0 bg-slate-50 z-10 shadow-[1px_0_0_#e2e8f0] min-w-[13rem]">Learner</th>
                <th class="min-w-[9rem]">Attendance</th>
                <th v-for="s in reg.sessions" :key="s.id" class="text-center !normal-case !tracking-normal min-w-[5.5rem]" :title="`${s.title}: ${s.present} of ${s.expected} attended`">
                  <span class="block text-xs font-semibold text-slate-700 truncate max-w-[7rem] mx-auto">{{ s.title }}</span>
                  <span class="block text-xs font-normal text-slate-500">{{ shortDate(s.starts_at) }}</span>
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-if="!regRows.length"><td :colspan="2 + reg.sessions.length" class="text-center text-slate-500 py-8">{{ onlyAtRisk ? 'Nobody needs attention right now.' : 'No learners enrolled yet.' }}</td></tr>
              <tr v-for="r in regRows" :key="r.user.id" class="group hover:bg-slate-50">
                <td class="sticky left-0 bg-white group-hover:bg-slate-50 z-10 shadow-[1px_0_0_#e2e8f0]">
                  <div class="flex items-start gap-2">
                    <div class="min-w-0 flex-1">
                      <div class="font-semibold text-slate-900 truncate">{{ r.user.full_name }}</div>
                      <div v-if="r.at_risk" class="text-xs text-amber-700 flex items-center gap-1"><AlertTriangle class="w-3 h-3 shrink-0" /> {{ riskReason(r) }}</div>
                      <div v-else class="text-xs text-slate-500 truncate">{{ r.user.email }}</div>
                    </div>
                    <a v-if="r.at_risk" :href="`mailto:${r.user.email}?subject=${encodeURIComponent('We missed you in class: ' + reg.course.title)}`"
                      class="p-1.5 rounded-lg text-slate-500 hover:text-brand-700 hover:bg-brand-50 shrink-0" :aria-label="`Email ${r.user.full_name}`"><Mail class="w-4 h-4" /></a>
                  </div>
                </td>
                <td>
                  <div v-if="r.rate !== null" class="flex items-center gap-2">
                    <div class="h-2 w-16 rounded-full bg-slate-100 overflow-hidden"><div class="h-full rounded-full" :class="rateClass(r.rate)" :style="`width:${r.rate}%`" /></div>
                    <span class="text-sm tabular-nums font-semibold">{{ r.rate }}%</span>
                  </div>
                  <span v-else class="text-sm text-slate-500">No classes yet</span>
                  <div class="text-xs text-slate-500">{{ r.present }} of {{ r.eligible }}</div>
                </td>
                <td v-for="c in r.cells" :key="c.session_id" class="text-center">
                  <span v-if="c.status === 'present'" class="inline-flex w-6 h-6 rounded-full bg-brand-50 text-brand-700 items-center justify-center" :title="`Joined ${dateTime(c.joined_at)}`">
                    <Check class="w-3.5 h-3.5" /><span class="sr-only">Present</span>
                  </span>
                  <span v-else-if="c.status === 'absent'" class="inline-flex w-6 h-6 rounded-full bg-rose-50 text-rose-600 items-center justify-center text-xs font-bold" title="Absent">
                    ✕<span class="sr-only">Absent</span>
                  </span>
                  <span v-else class="inline-flex w-6 h-6 items-center justify-center text-slate-400" title="Enrolled after this class">
                    <Minus class="w-3.5 h-3.5" /><span class="sr-only">Not enrolled yet</span>
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="text-xs text-slate-500 mt-3">
          A class counts towards a learner's attendance only if it happened after they enrolled. "Need attention" means below
          {{ reg.thresholds.rate }}% or missing the last {{ reg.thresholds.missed_in_a_row }} classes in a row. Present means the learner joined through Infohive.
        </p>
      </template>
    </template>

    <template v-else>
    <div v-if="loading" class="space-y-3"><div v-for="i in 2" :key="i" class="card h-20 animate-pulse" /></div>
    <div v-else-if="!data.sessions.length" class="card p-10 text-center text-slate-500">
      <Video class="w-10 h-10 mx-auto mb-2 text-slate-300" />
      <p class="font-semibold text-slate-700">No live classes yet</p>
      <p class="text-sm mt-1">Run a kick-off, weekly Q&amp;A or office hours with your students.</p>
    </div>
    <div v-else class="space-y-3">
      <div v-for="s in data.sessions" :key="s.id" class="card p-4 sm:p-5">
        <div class="flex flex-wrap items-start gap-3">
          <div class="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
            :class="s.state === 'live' ? 'bg-rose-500 text-white' : 'bg-brand-50 text-brand-600'">
            <component :is="s.state === 'live' ? Radio : s.provider === 'external' ? ExternalLink : Video" class="w-5 h-5" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="font-bold text-slate-800" :class="s.status === 'cancelled' && 'line-through text-slate-400'">{{ s.title }}</h3>
              <span class="badge" :class="stateBadge[s.state]?.[1]">{{ stateBadge[s.state]?.[0] }}</span>
            </div>
            <p class="text-xs text-slate-500 mt-0.5">{{ when(s.starts_at) }} · {{ fmtMinutes(s.duration_minutes) }} ·
              {{ s.provider === 'external' ? 'External link' : 'Built-in video room' }} ·
              <template v-if="s.state === 'live' || s.state === 'ended'"><span class="font-semibold text-slate-600">{{ s.attendance_count }}/{{ data.enrolled }}</span> attended</template><template v-else>{{ data.enrolled }} enrolled</template></p>
            <p v-if="s.recording_url" class="text-xs text-brand-700 mt-1 flex items-center gap-1"><PlayCircle class="w-3.5 h-3.5" /> Recording linked</p>
          </div>
        </div>
        <div class="mt-3 flex flex-wrap gap-1.5">
          <NuxtLink v-if="s.status !== 'cancelled' && s.state !== 'ended'" :to="`/live/${s.id}`" class="btn-primary text-xs !px-3 !py-1.5">
            <Video class="w-3.5 h-3.5" /> {{ s.state === 'live' || s.state === 'starting_soon' ? 'Start / join' : 'Open room' }}
          </NuxtLink>
          <button v-if="s.state === 'live' || s.state === 'ended'" class="btn-secondary text-xs !px-3 !py-1.5" @click="openAttendance(s)"><Users class="w-3.5 h-3.5" /> Attendance</button>
          <button v-if="s.status !== 'cancelled'" class="btn-secondary text-xs !px-3 !py-1.5" @click="openForm(s)">
            <Pencil class="w-3.5 h-3.5" /> {{ s.state === 'ended' ? 'Add recording' : 'Edit' }}
          </button>
          <button v-if="s.status !== 'cancelled' && s.state !== 'ended'" class="btn-ghost text-xs !px-3 !py-1.5 text-amber-700" @click="cancelSession(s)"><Ban class="w-3.5 h-3.5" /> Cancel</button>
          <button class="btn-ghost text-xs !px-3 !py-1.5 text-rose-600" @click="removeSession(s)"><Trash2 class="w-3.5 h-3.5" /> Delete</button>
        </div>
      </div>
    </div>

    </template>

    <!-- schedule / edit -->
    <Modal :open="modal.open" :title="modal.editing ? 'Edit live class' : 'Schedule a live class'" @close="modal = { open: false }">
      <div class="space-y-4">
        <div><label class="label" for="teach-courses-id-liv-form-title">Title</label><input id="teach-courses-id-liv-form-title" v-model="form.title" class="input" placeholder="e.g. Week 1 kick-off & Q&A" /></div>
        <div class="grid sm:grid-cols-[1fr_8rem] gap-3">
          <div><label class="label" for="teach-courses-id-liv-form-starts_local">Starts</label><input id="teach-courses-id-liv-form-starts_local" v-model="form.starts_local" type="datetime-local" class="input" /></div>
          <div><label class="label" for="teach-courses-id-liv-form-duration_minutes">Length (min)</label><input id="teach-courses-id-liv-form-duration_minutes" v-model.number="form.duration_minutes" type="number" min="10" max="600" step="5" class="input" /></div>
        </div>
        <p class="text-xs text-slate-500 -mt-2">Times are in your timezone ({{ tz }}); students see them in theirs.</p>
        <div>
          <label class="label">Where</label>
          <div class="grid sm:grid-cols-2 gap-2">
            <label class="flex gap-2 p-3 rounded-xl border cursor-pointer" :class="form.provider === 'jitsi' ? 'border-brand-500 bg-brand-50/50' : 'border-slate-200'">
              <input v-model="form.provider" type="radio" value="jitsi" class="mt-1 accent-brand-600" />
              <span><b class="text-sm text-slate-800">Built-in video room</b><span class="block text-xs text-slate-500">Video, screen sharing and chat inside Infohive</span></span>
            </label>
            <label class="flex gap-2 p-3 rounded-xl border cursor-pointer" :class="form.provider === 'external' ? 'border-brand-500 bg-brand-50/50' : 'border-slate-200'">
              <input v-model="form.provider" type="radio" value="external" class="mt-1 accent-brand-600" />
              <span><b class="text-sm text-slate-800">External link</b><span class="block text-xs text-slate-500">Zoom, Google Meet, Teams…</span></span>
            </label>
          </div>
        </div>
        <div v-if="form.provider === 'external'">
          <label class="label" for="teach-courses-id-liv-form-external_url">Meeting link</label>
          <input id="teach-courses-id-liv-form-external_url" v-model="form.external_url" class="input" placeholder="https://zoom.us/j/…" />
          <p class="text-xs text-slate-500 mt-1">Only enrolled students get this link, and only when the class opens.</p>
        </div>
        <div><label class="label" for="teach-courses-id-liv-form-description">Description <span class="text-slate-500 font-normal">(optional)</span></label><textarea id="teach-courses-id-liv-form-description" v-model="form.description" rows="3" class="input" placeholder="Agenda, what to prepare…" /></div>
        <div v-if="modal.editing">
          <label class="label" for="teach-courses-id-liv-form-recording_url">Recording link <span class="text-slate-500 font-normal">(after the class)</span></label>
          <input id="teach-courses-id-liv-form-recording_url" v-model="form.recording_url" class="input" placeholder="YouTube, Vimeo or .mp4 link" />
          <p class="text-xs text-slate-500 mt-1">Students watch it inside Infohive, with the same watch-only player as lessons.</p>
        </div>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <button class="btn-secondary" @click="modal = { open: false }">Cancel</button>
          <button class="btn-primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : modal.editing ? 'Save changes' : 'Schedule & notify' }}</button>
        </div>
      </template>
    </Modal>

    <!-- attendance -->
    <Modal :open="!!att" :title="att ? `Attendance - ${att.session.title}` : ''" @close="att = null">
      <template v-if="att">
        <div class="flex items-center justify-between gap-3 mb-3">
          <p class="text-sm text-slate-600"><b class="text-slate-800">{{ att.present }}</b> of {{ att.total }} enrolled students joined.</p>
          <button v-if="att.rows.length" class="btn-secondary text-sm !py-1.5" @click="exportSession"><Download class="w-4 h-4" /> CSV</button>
        </div>
        <ul class="divide-y divide-slate-100 border border-slate-100 rounded-xl">
          <li v-for="r in att.rows" :key="r.user.id" class="flex items-center gap-3 px-3 py-2.5 text-sm">
            <span class="w-2 h-2 rounded-full shrink-0" :class="r.present ? 'bg-brand-500' : 'bg-slate-300'" />
            <span class="flex-1 min-w-0"><span class="font-medium text-slate-800">{{ r.user.full_name }}</span><span class="block text-xs text-slate-500 truncate">{{ r.user.email }}</span></span>
            <span class="text-xs" :class="r.present ? 'text-brand-700' : 'text-slate-400'">{{ r.present ? `Joined ${new Date(r.first_joined_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}` : absentLabel }}</span>
          </li>
          <li v-if="!att.rows.length" class="px-3 py-6 text-center text-sm text-slate-500">No students enrolled yet.</li>
        </ul>
      </template>
    </Modal>
  </div>
</template>
