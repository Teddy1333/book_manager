const API_BASE = "http://127.0.0.1:8000";
const state = {
  token: localStorage.getItem("bookJournalToken") || "",
  books: [],
  selectedBookId: null,
  tags: new Set(),
  recorder: null,
  chunks: [],
  isRecording: false,
};

const $ = (selector) => document.querySelector(selector);
const els = {
  authForm: $("#authForm"),
  signupBtn: $("#signupBtn"),
  username: $("#username"),
  password: $("#password"),
  refreshBooksBtn: $("#refreshBooksBtn"),
  bookGrid: $("#bookGrid"),
  bookFilter: $("#bookFilter"),
  tagFilter: $("#tagFilter"),
  bookForm: $("#bookForm"),
  bookSearch: $("#bookSearch"),
  lookupBtn: $("#lookupBtn"),
  lookupResults: $("#lookupResults"),
  bookTitle: $("#bookTitle"),
  bookAuthor: $("#bookAuthor"),
  bookIsbn: $("#bookIsbn"),
  bookPages: $("#bookPages"),
  bookPublisher: $("#bookPublisher"),
  bookCover: $("#bookCover"),
  bookDescription: $("#bookDescription"),
  tagEntry: $("#tagEntry"),
  tagList: $("#tagList"),
  hiddenPhotoInput: $("#hiddenPhotoInput"),
  photoBookBtn: $("#photoBookBtn"),
  voiceBookBtn: $("#voiceBookBtn"),
  progressBook: $("#progressBook"),
  progressPage: $("#progressPage"),
  progressTotal: $("#progressTotal"),
  manualProgressBtn: $("#manualProgressBtn"),
  progressPhoto: $("#progressPhoto"),
  photoProgressBtn: $("#photoProgressBtn"),
  notesBook: $("#notesBook"),
  notePage: $("#notePage"),
  noteText: $("#noteText"),
  saveNoteBtn: $("#saveNoteBtn"),
  notesList: $("#notesList"),
  canvas: $("#notesCanvas"),
  penColor: $("#penColor"),
  penSize: $("#penSize"),
  clearCanvasBtn: $("#clearCanvasBtn"),
  convertHandwritingBtn: $("#convertHandwritingBtn"),
  recordVoiceBtn: $("#recordVoiceBtn"),
  recordingStatus: $("#recordingStatus"),
  shareModal: $("#shareModal"),
  openShareBtn: $("#openShareBtn"),
  closeShareBtn: $("#closeShareBtn"),
  shareBook: $("#shareBook"),
  createShareBtn: $("#createShareBtn"),
  copyShareBtn: $("#copyShareBtn"),
  nativeShareModalBtn: $("#nativeShareModalBtn"),
  shareLink: $("#shareLink"),
  qrBox: $("#qrBox"),
  toast: $("#toast"),
  statBooks: $("#statBooks"),
  statNotes: $("#statNotes"),
  statPages: $("#statPages"),
  statSuggestions: $("#statSuggestions"),
};

function showToast(message, type = "info") {
  els.toast.textContent = message;
  els.toast.style.borderColor = type === "error" ? "rgba(255, 107, 129, 0.72)" : "var(--line)";
  els.toast.classList.add("is-visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => els.toast.classList.remove("is-visible"), 3600);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof FormData) && !(options.body instanceof Blob) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(Array.isArray(error.detail) ? error.detail.map((item) => item.msg).join(", ") : error.detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function bookProgress(book) {
  const latest = book.latest_progress;
  const total = Number(latest?.total_pages || book.pages || 0);
  const current = Number(latest?.current_page || 0);
  const percent = latest?.percentage ?? (total ? Math.round((current / total) * 100) : 0);
  return { current, total, percent: Math.min(100, Math.max(0, Number(percent) || 0)) };
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

function renderBooks() {
  const q = els.bookFilter.value.trim().toLowerCase();
  const selectedTag = els.tagFilter.value;
  const books = state.books.filter((book) => {
    const haystack = [book.title, book.author, book.isbn, ...(book.tags || [])].join(" ").toLowerCase();
    return (!q || haystack.includes(q)) && (!selectedTag || book.tags?.includes(selectedTag));
  });

  if (!books.length) {
    els.bookGrid.innerHTML = `<article class="book-card"><p class="muted">No books found. Search Google Books or add one manually.</p></article>`;
    return;
  }

  els.bookGrid.innerHTML = books.map((book) => {
    const progress = bookProgress(book);
    const cover = book.cover_url
      ? `<img src="${escapeHtml(book.cover_url)}" alt="${escapeHtml(book.title)} cover">`
      : `<i class="fa-solid fa-book-open"></i>`;
    return `
      <article class="book-card" data-book-id="${book.id}">
        <div class="book-card-top">
          <div class="cover">${cover}</div>
          <div>
            <h3 class="book-title">${escapeHtml(book.title)}</h3>
            <p class="muted">${escapeHtml(book.author || "Unknown author")}</p>
          </div>
        </div>
        <div>
          <div class="progress-bar" aria-label="${progress.percent}% complete">
            <span style="--progress:${progress.percent}%"></span>
          </div>
          <p class="muted">${progress.current} / ${progress.total || "?"} pages · ${progress.percent}%</p>
        </div>
        <div class="quick-links">
          <a href="#notes" data-action="select-notes" data-id="${book.id}"><i class="fa-solid fa-pen"></i> Add Note</a>
          <a href="#progress" data-action="select-progress" data-id="${book.id}"><i class="fa-solid fa-chart-simple"></i> Track Progress</a>
          <a href="#" data-action="share-modal" data-id="${book.id}"><i class="fa-solid fa-qrcode"></i> Share via Link/QR</a>
        </div>
        <div class="card-actions">
          <button class="secondary-btn" type="button" data-action="native-share" data-id="${book.id}">
            <i class="fa-solid fa-share-nodes"></i> Native Share
          </button>
        </div>
      </article>
    `;
  }).join("");
}

function renderTags() {
  const tags = [...new Set(state.books.flatMap((book) => book.tags || []))].sort();
  els.tagFilter.innerHTML = `<option value="">All tags</option>${tags.map((tag) => `<option value="${escapeHtml(tag)}">${escapeHtml(tag)}</option>`).join("")}`;
}

function renderBookSelects() {
  const options = state.books.map((book) => `<option value="${book.id}">${escapeHtml(book.title)}</option>`).join("");
  [els.progressBook, els.notesBook, els.shareBook].forEach((select) => {
    select.innerHTML = options || `<option value="">No books yet</option>`;
  });
  if (!state.selectedBookId && state.books[0]) state.selectedBookId = state.books[0].id;
  [els.progressBook, els.notesBook, els.shareBook].forEach((select) => {
    if (state.selectedBookId) select.value = String(state.selectedBookId);
  });
}

function renderTagInput() {
  els.tagList.innerHTML = [...state.tags].map((tag) => `
    <button class="chip" type="button" data-remove-tag="${escapeHtml(tag)}">
      ${escapeHtml(tag)} <i class="fa-solid fa-xmark"></i>
    </button>
  `).join("");
}

function fillBookForm(book) {
  els.bookTitle.value = book.title || "";
  els.bookAuthor.value = book.author || "";
  els.bookIsbn.value = book.isbn || "";
  els.bookPages.value = book.pages || "";
  els.bookPublisher.value = book.publisher || "";
  els.bookCover.value = book.cover_url || "";
  els.bookDescription.value = book.description || "";
  state.tags = new Set(book.tags || []);
  renderTagInput();
}

async function loadBooks() {
  if (!state.token) {
    renderBooks();
    return;
  }
  els.refreshBooksBtn.classList.add("is-loading");
  try {
    const [books, stats, suggestions] = await Promise.all([
      api("/books"),
      api("/user/stats").catch(() => null),
      api("/suggestions").catch(() => []),
    ]);
    state.books = books;
    els.statBooks.textContent = stats?.books_count ?? books.length;
    els.statNotes.textContent = stats?.notes_count ?? "0";
    els.statPages.textContent = stats?.total_read_pages ?? "0";
    els.statSuggestions.textContent = Array.isArray(suggestions) ? suggestions.length : "0";
    renderTags();
    renderBookSelects();
    renderBooks();
  } catch (error) {
    showToast(error.message || "Could not load books", "error");
  } finally {
    els.refreshBooksBtn.classList.remove("is-loading");
  }
}

async function login(event) {
  event.preventDefault();
  const body = new URLSearchParams();
  body.set("username", els.username.value.trim());
  body.set("password", els.password.value);
  try {
    const data = await api("/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    state.token = data.access_token;
    localStorage.setItem("bookJournalToken", state.token);
    showToast("Connected to the Book Diary API");
    await loadBooks();
  } catch (error) {
    showToast(error.message || "Login failed", "error");
  }
}

async function signup() {
  try {
    const query = new URLSearchParams({ username: els.username.value.trim(), password: els.password.value });
    await api(`/signup?${query.toString()}`, { method: "POST" });
    showToast("Account created. Logging in next.");
    els.authForm.requestSubmit();
  } catch (error) {
    showToast(error.message || "Signup failed", "error");
  }
}

async function lookupBooks() {
  const query = els.bookSearch.value.trim();
  if (!query) return showToast("Enter a title, author, keyword, or ISBN.", "error");
  els.lookupResults.innerHTML = `<p class="muted">Searching Google Books...</p>`;
  try {
    const results = await api(`/lookup/google?q=${encodeURIComponent(query)}&limit=5`);
    els.lookupResults.innerHTML = results.map((book, index) => `
      <button class="lookup-item" type="button" data-lookup-index="${index}">
        <strong>${escapeHtml(book.title || "Untitled")}</strong>
        <span class="muted">${escapeHtml(book.author || "Unknown author")} · ${escapeHtml(book.pages || "?")} pages</span>
      </button>
    `).join("") || `<p class="muted">No matches found.</p>`;
    els.lookupResults._results = results;
  } catch (error) {
    els.lookupResults.innerHTML = "";
    showToast(error.message || "Lookup failed", "error");
  }
}

async function createBook(event) {
  event.preventDefault();
  const payload = {
    title: els.bookTitle.value.trim(),
    author: els.bookAuthor.value.trim() || null,
    isbn: els.bookIsbn.value.trim() || null,
    publisher: els.bookPublisher.value.trim() || null,
    pages: els.bookPages.value.trim() || null,
    description: els.bookDescription.value.trim() || null,
    cover_url: els.bookCover.value.trim() || null,
    source: "frontend",
    tags: [...state.tags],
  };
  try {
    await api("/books", { method: "POST", body: JSON.stringify(payload) });
    els.bookForm.reset();
    state.tags.clear();
    renderTagInput();
    showToast("Book saved");
    await loadBooks();
  } catch (error) {
    showToast(error.message || "Could not save book", "error");
  }
}

async function recognizeBookFromPhoto(file) {
  try {
    const data = await api("/books/photo/recognize", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: await file.arrayBuffer(),
    });
    if (data.matches?.[0]) fillBookForm(data.matches[0]);
    showToast("Photo processed with AI book recognition");
  } catch (error) {
    showToast(error.message || "Photo recognition failed", "error");
  }
}

async function recognizeBookFromVoice() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    return showToast("Voice capture is not supported in this browser.", "error");
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = (event) => chunks.push(event.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      try {
        const data = await api("/books/voice/recognize?audio_format=webm", {
          method: "POST",
          headers: { "Content-Type": "application/octet-stream" },
          body: await blob.arrayBuffer(),
        });
        if (data.matches?.[0]) fillBookForm(data.matches[0]);
        showToast("Voice search processed");
      } catch (error) {
        showToast(error.message || "Voice recognition failed", "error");
      }
    };
    recorder.start();
    showToast("Recording book voice input for 5 seconds...");
    setTimeout(() => recorder.stop(), 5000);
  } catch (error) {
    showToast(error.message || "Microphone permission denied", "error");
  }
}

async function addManualProgress() {
  const bookId = els.progressBook.value;
  if (!bookId) return showToast("Select a book first.", "error");
  const payload = {
    current_page: Number(els.progressPage.value || 0),
    total_pages: els.progressTotal.value ? Number(els.progressTotal.value) : null,
    source: "manual_frontend",
  };
  try {
    await api(`/books/${bookId}/progress`, { method: "POST", body: JSON.stringify(payload) });
    showToast("Progress tracked");
    await loadBooks();
  } catch (error) {
    showToast(error.message || "Could not track progress", "error");
  }
}

async function addPhotoProgress() {
  const bookId = els.progressBook.value;
  const file = els.progressPhoto.files?.[0];
  if (!bookId || !file) return showToast("Select a book and upload a page photo.", "error");
  try {
    await api(`/books/${bookId}/progress/photo`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: await file.arrayBuffer(),
    });
    showToast("AI progress photo processed");
    await loadBooks();
  } catch (error) {
    showToast(error.message || "Could not process page photo", "error");
  }
}

async function saveTypedNote() {
  const bookId = els.notesBook.value;
  const text = els.noteText.value.trim();
  if (!bookId || !text) return showToast("Select a book and write a note.", "error");
  try {
    await api(`/books/${bookId}/notes`, {
      method: "POST",
      body: JSON.stringify({ text, page: els.notePage.value ? Number(els.notePage.value) : null, note_type: "manual_frontend" }),
    });
    els.noteText.value = "";
    showToast("Note saved");
    await loadNotes(bookId);
    await loadBooks();
  } catch (error) {
    showToast(error.message || "Could not save note", "error");
  }
}

async function convertCanvasToText() {
  const bookId = els.notesBook.value;
  if (!bookId) return showToast("Select a book first.", "error");
  els.canvas.toBlob(async (blob) => {
    try {
      const note = await api(`/books/${bookId}/notes/photo?is_handwritten=true${els.notePage.value ? `&page=${els.notePage.value}` : ""}`, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: await blob.arrayBuffer(),
      });
      els.noteText.value = note.text || "";
      showToast("Handwriting converted and saved");
      await loadNotes(bookId);
      await loadBooks();
    } catch (error) {
      showToast(error.message || "Handwriting conversion failed", "error");
    }
  }, "image/png");
}

async function toggleVoiceNote() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    return showToast("Voice notes are not supported in this browser.", "error");
  }
  if (!state.isRecording) {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.chunks = [];
    state.recorder = new MediaRecorder(stream);
    state.recorder.ondataavailable = (event) => state.chunks.push(event.data);
    state.recorder.onstop = () => submitVoiceNote(stream);
    state.recorder.start();
    state.isRecording = true;
    els.recordingStatus.textContent = "Recording";
    els.recordVoiceBtn.innerHTML = `<span>✨</span><i class="fa-solid fa-stop"></i> Stop Voice Note`;
    return;
  }
  state.recorder.stop();
}

async function submitVoiceNote(stream) {
  stream.getTracks().forEach((track) => track.stop());
  state.isRecording = false;
  els.recordingStatus.textContent = "Processing";
  els.recordVoiceBtn.innerHTML = `<span>✨</span><i class="fa-solid fa-microphone-lines"></i> Start Voice Note`;
  const bookId = els.notesBook.value;
  const blob = new Blob(state.chunks, { type: state.recorder.mimeType || "audio/webm" });
  try {
    await api(`/books/${bookId}/notes/voice?audio_format=webm${els.notePage.value ? `&page=${els.notePage.value}` : ""}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: await blob.arrayBuffer(),
    });
    els.recordingStatus.textContent = "Idle";
    showToast("Voice note transcribed and saved");
    await loadNotes(bookId);
    await loadBooks();
  } catch (error) {
    els.recordingStatus.textContent = "Idle";
    showToast(error.message || "Voice note failed", "error");
  }
}

async function loadNotes(bookId = els.notesBook.value) {
  if (!bookId || !state.token) return;
  try {
    const notes = await api(`/books/${bookId}/notes`);
    els.notesList.innerHTML = notes.map((note) => `
      <article class="note-item">
        <p>${escapeHtml(note.text)}</p>
        <small class="muted">${note.note_type} ${note.page !== null ? `· page ${note.page}` : ""}</small>
      </article>
    `).join("") || `<p class="muted">No notes yet.</p>`;
  } catch (error) {
    showToast(error.message || "Could not load notes", "error");
  }
}

async function createShareLink() {
  const bookId = els.shareBook.value;
  if (!bookId) return showToast("Select a book first.", "error");
  try {
    const data = await api(`/books/${bookId}/share`, { method: "POST" });
    els.shareLink.value = data.share_url;
    els.qrBox.innerHTML = `<img src="${escapeHtml(data.qr_url)}" alt="QR code for sharing link">`;
    showToast(data.verified ? "Share link verified" : "Share link created");
  } catch (error) {
    showToast(error.message || "Could not create share link", "error");
  }
}

async function nativeShare(book) {
  const title = book?.title || "Book Journal share";
  const text = book ? `${book.title} by ${book.author || "Unknown author"}` : "Shared from The Book Journal & Diary";
  const url = els.shareLink.value || window.location.href;
  if (navigator.share) {
    await navigator.share({ title, text, url }).catch(() => {});
  } else {
    await navigator.clipboard.writeText(url);
    showToast("Native share unavailable. Link copied instead.");
  }
}

function openShareModal(bookId = state.selectedBookId) {
  if (bookId) {
    state.selectedBookId = Number(bookId);
    els.shareBook.value = String(bookId);
  }
  els.shareModal.classList.add("is-open");
  els.shareModal.setAttribute("aria-hidden", "false");
}

function closeShareModal() {
  els.shareModal.classList.remove("is-open");
  els.shareModal.setAttribute("aria-hidden", "true");
}

function initCanvas() {
  const ctx = els.canvas.getContext("2d");
  let drawing = false;
  let last = null;
  const point = (event) => {
    const rect = els.canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * (els.canvas.width / rect.width),
      y: (event.clientY - rect.top) * (els.canvas.height / rect.height),
    };
  };
  els.canvas.addEventListener("pointerdown", (event) => {
    drawing = true;
    last = point(event);
    els.canvas.setPointerCapture(event.pointerId);
  });
  els.canvas.addEventListener("pointermove", (event) => {
    if (!drawing) return;
    const current = point(event);
    ctx.strokeStyle = els.penColor.value;
    ctx.lineWidth = Number(els.penSize.value);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(last.x, last.y);
    ctx.lineTo(current.x, current.y);
    ctx.stroke();
    last = current;
  });
  ["pointerup", "pointercancel", "pointerleave"].forEach((name) => {
    els.canvas.addEventListener(name, () => {
      drawing = false;
      last = null;
    });
  });
  els.clearCanvasBtn.addEventListener("click", () => ctx.clearRect(0, 0, els.canvas.width, els.canvas.height));
}

function bindEvents() {
  els.authForm.addEventListener("submit", login);
  els.signupBtn.addEventListener("click", signup);
  els.refreshBooksBtn.addEventListener("click", loadBooks);
  els.bookFilter.addEventListener("input", renderBooks);
  els.tagFilter.addEventListener("change", renderBooks);
  els.lookupBtn.addEventListener("click", lookupBooks);
  els.bookSearch.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      lookupBooks();
    }
  });
  els.lookupResults.addEventListener("click", (event) => {
    const item = event.target.closest("[data-lookup-index]");
    if (item) fillBookForm(els.lookupResults._results[Number(item.dataset.lookupIndex)]);
  });
  els.bookForm.addEventListener("submit", createBook);
  els.tagEntry.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && els.tagEntry.value.trim()) {
      event.preventDefault();
      state.tags.add(els.tagEntry.value.trim().toLowerCase());
      els.tagEntry.value = "";
      renderTagInput();
    }
  });
  els.tagList.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-remove-tag]");
    if (chip) {
      state.tags.delete(chip.dataset.removeTag);
      renderTagInput();
    }
  });
  els.photoBookBtn.addEventListener("click", () => {
    els.hiddenPhotoInput.onchange = () => els.hiddenPhotoInput.files[0] && recognizeBookFromPhoto(els.hiddenPhotoInput.files[0]);
    els.hiddenPhotoInput.click();
  });
  els.voiceBookBtn.addEventListener("click", recognizeBookFromVoice);
  els.manualProgressBtn.addEventListener("click", addManualProgress);
  els.photoProgressBtn.addEventListener("click", addPhotoProgress);
  els.saveNoteBtn.addEventListener("click", saveTypedNote);
  els.convertHandwritingBtn.addEventListener("click", convertCanvasToText);
  els.recordVoiceBtn.addEventListener("click", toggleVoiceNote);
  els.notesBook.addEventListener("change", () => loadNotes(els.notesBook.value));
  els.openShareBtn.addEventListener("click", () => openShareModal());
  els.closeShareBtn.addEventListener("click", closeShareModal);
  els.createShareBtn.addEventListener("click", createShareLink);
  els.copyShareBtn.addEventListener("click", async () => {
    await navigator.clipboard.writeText(els.shareLink.value);
    showToast("Sharing link copied");
  });
  els.nativeShareModalBtn.addEventListener("click", () => nativeShare(state.books.find((book) => String(book.id) === els.shareBook.value)));
  els.shareModal.addEventListener("click", (event) => {
    if (event.target === els.shareModal) closeShareModal();
  });
  els.bookGrid.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-action]");
    if (!action) return;
    const bookId = action.dataset.id;
    const book = state.books.find((item) => String(item.id) === String(bookId));
    state.selectedBookId = Number(bookId);
    if (action.dataset.action === "select-notes") {
      els.notesBook.value = bookId;
      await loadNotes(bookId);
    }
    if (action.dataset.action === "select-progress") els.progressBook.value = bookId;
    if (action.dataset.action === "share-modal") {
      event.preventDefault();
      openShareModal(bookId);
    }
    if (action.dataset.action === "native-share") await nativeShare(book);
  });
}

bindEvents();
initCanvas();
renderTagInput();
loadBooks();
