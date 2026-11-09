// Site-wide behaviour: the light/dark switch, the rotating "typewriter" word,
// and the home page's scroll reveal and AI answer replay. Nothing here changes
// server-rendered content outside those widgets, so text such as the A/B
// button is never touched.
(function () {
  "use strict";

  var root = document.documentElement;
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Theme switch ---------- */
  function currentTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function syncSwitches() {
    var dark = currentTheme() === "dark";
    document.querySelectorAll("[data-theme-switch]").forEach(function (el) {
      el.setAttribute("aria-checked", dark ? "true" : "false");
    });
  }

  document.querySelectorAll("[data-theme-switch]").forEach(function (el) {
    el.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("theme", next);
      } catch (e) {
        /* private mode: the choice just isn't remembered */
      }
      syncSwitches();
    });
  });
  syncSwitches();

  /* ---------- After a failed form submit, bring the problem into view ----------
     Fields don't autofocus (on phones that would skip the intro), so when the
     server sends a form back with errors, scroll to and focus the first one. */
  var firstProblem = document.querySelector(".form-alert, .field-invalid");
  if (firstProblem) {
    var form = firstProblem.closest("form");
    var input = form && (form.querySelector(".field-invalid input") || form.querySelector(".field input"));
    var reveal = function () {
      // after "load", so the browser's own scroll restoration doesn't undo it
      firstProblem.scrollIntoView({ block: "center", behavior: "instant" });
      if (input) input.focus({ preventScroll: true });
    };
    if (document.readyState === "complete") reveal();
    else window.addEventListener("load", function () { setTimeout(reveal, 0); });
  }

  /* ---------- Rotating word ----------
     Markup (the server renders the first word, so it reads fine without JS):

       <span class="rotate" data-rotate="who you are|your budget|your story">
         <span class="rotate-word" aria-hidden="true">who you are</span><span
               class="rotate-caret" aria-hidden="true"></span>
         <span class="visually-hidden">who you are</span>
       </span>

     Screen readers only ever hear the hidden copy, never the letter-by-letter
     changes. With reduced motion the first word just stays put. */
  function startRotator(el) {
    var words = (el.getAttribute("data-rotate") || "").split("|").filter(Boolean);
    var target = el.querySelector(".rotate-word");
    if (!target || words.length < 2 || reducedMotion) return;

    // Reserve the widest word's width so the line never reflows while typing.
    var widest = 0;
    words.forEach(function (w) {
      target.textContent = w;
      widest = Math.max(widest, target.getBoundingClientRect().width);
    });
    target.textContent = words[0];
    // In em, so it still fits when the headline's font size changes (resize, rotation).
    var fontSize = parseFloat(getComputedStyle(el).fontSize) || 16;
    el.style.display = "inline-block";
    el.style.minWidth = ((widest + 4) / fontSize).toFixed(3) + "em";
    el.style.maxWidth = "100%";
    el.style.textAlign = "left";
    el.classList.add("is-typing");

    var i = 0;
    var text = words[0];
    var deleting = true;

    function tick() {
      if (document.hidden) return setTimeout(tick, 600);
      var word = words[i];
      if (deleting) {
        text = text.slice(0, -1);
        target.textContent = text;
        if (!text) {
          deleting = false;
          i = (i + 1) % words.length;
          return setTimeout(tick, 280);
        }
        return setTimeout(tick, 34);
      }
      text = word.slice(0, text.length + 1);
      target.textContent = text;
      if (text === word) {
        deleting = true;
        return setTimeout(tick, 2200);
      }
      return setTimeout(tick, 68);
    }

    setTimeout(tick, 2200);
  }

  function initRotators() {
    document.querySelectorAll("[data-rotate]").forEach(startRotator);
  }

  // Measure after web/system fonts settle so the reserved width is right.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(initRotators);
  } else {
    window.addEventListener("load", initRotators);
  }

  /* ---------- Home page: scroll reveal and AI answer streaming ----------
     Both are decoration on top of server-rendered content: without JS, or with
     reduced motion, everything is simply shown in its final state.

     [data-reveal]  fades up the first time it scrolls into view. Elements
                    already on screen at load are left alone (no flash).
     [data-stream]  replays an AI answer while visible: "thinking" dots, then
                    the [data-stream-text] words one by one, then the citations. */
  if (reducedMotion || !("IntersectionObserver" in window)) return;

  var revealer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.remove("reveal-wait");
        revealer.unobserve(entry.target);
      });
    },
    { rootMargin: "0px 0px -12% 0px" }
  );

  document.querySelectorAll("[data-reveal]").forEach(function (el) {
    if (el.getBoundingClientRect().top < window.innerHeight * 0.88) return;
    el.classList.add("reveal-wait");
    revealer.observe(el);
  });

  function streamer(el) {
    var textEl = el.querySelector("[data-stream-text]");
    if (!textEl) return null;
    // Wrap every word once. The full answer stays laid out at its final size;
    // replaying only fades words in, so the card never grows or jumps.
    var words = textEl.textContent.trim().split(/\s+/);
    textEl.textContent = "";
    var toks = words.map(function (word, i) {
      if (i) textEl.appendChild(document.createTextNode(" "));
      var tok = document.createElement("span");
      tok.className = "tok";
      tok.textContent = word;
      textEl.appendChild(tok);
      return tok;
    });
    var visible = false;
    var running = false;

    function play() {
      if (!visible || document.hidden) {
        running = false;
        return;
      }
      running = true;
      toks.forEach(function (tok) {
        tok.classList.remove("on", "last");
      });
      el.classList.add("is-replaying", "is-thinking");
      setTimeout(function () {
        el.classList.remove("is-thinking");
        el.classList.add("is-streaming");
        var i = 0;
        (function next() {
          if (i < toks.length) {
            if (i) toks[i - 1].classList.remove("last");
            toks[i++].classList.add("on", "last");
            return setTimeout(next, 45 + Math.random() * 70);
          }
          el.classList.remove("is-streaming");
          setTimeout(play, 6500);
        })();
      }, 1500);
    }

    return function (isVisible) {
      visible = isVisible;
      if (visible && !running) play();
    };
  }

  var streamWatch = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.target._stream) entry.target._stream(entry.isIntersecting);
      });
    },
    { threshold: 0.4 }
  );

  document.querySelectorAll("[data-stream]").forEach(function (el) {
    el._stream = streamer(el);
    if (el._stream) streamWatch.observe(el);
  });
})();
