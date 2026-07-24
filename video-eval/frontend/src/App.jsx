import { useEffect, useState } from "react";

// Le tre dimensioni valutate per ogni coppia.
const QUESTIONS = [
  { key: "preference", text: "Quale video preferisci in generale?" },
  { key: "relevance", text: "Quale è più pertinente al concetto richiesto?" },
  { key: "quality", text: "Quale ha la qualità video migliore?" },
];

const CHOICES = [
  { value: "A", label: "Video A" },
  { value: "tie", label: "Pari / indifferente" },
  { value: "B", label: "Video B" },
];

export default function App() {
  const [session, setSession] = useState(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/session")
      .then((r) => r.json())
      .then(setSession)
      .catch(() => setError("Impossibile caricare i video. Riprova più tardi."));
  }, []);

  if (error) {
    return (
      <Shell>
        <div className="notice">{error}</div>
      </Shell>
    );
  }

  if (!session) {
    return (
      <Shell>
        <div className="notice">Caricamento…</div>
      </Shell>
    );
  }

  if (done) {
    return (
      <Shell>
        <div className="finish">
          <h1>Fatto</h1>
          <p>Grazie, le tue risposte sono state registrate.</p>
        </div>
      </Shell>
    );
  }

  const items = session.items;
  const item = items[index];
  const total = items.length;
  const allAnswered = QUESTIONS.every((q) => answers[q.key]);

  function setAnswer(key, value) {
    setAnswers((prev) => ({ ...prev, [key]: value }));
  }

  async function submit() {
    setSubmitting(true);
    try {
      const res = await fetch("/api/vote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: session.session_id,
          concept: item.concept,
          system_A: item.system_A,
          system_B: item.system_B,
          preference: answers.preference,
          relevance: answers.relevance,
          quality: answers.quality,
        }),
      });
      if (!res.ok) throw new Error();
      // avanza
      setAnswers({});
      if (index + 1 < total) {
        setIndex(index + 1);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        setDone(true);
      }
    } catch {
      setError("Errore nell'invio del voto. Controlla la connessione e riprova.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Shell>
      <header className="head">
        <span className="eyebrow">Confronto {index + 1} di {total}</span>
        <h1>{item.label}</h1>
        <p className="lead">
          Guarda entrambi i video, poi rispondi alle tre domande.
        </p>
        <div className="progress">
          <div className="progress-fill" style={{ width: `${(index / total) * 100}%` }} />
        </div>
      </header>

      {item.reference && (
        <figure className="reference">
          <img src={item.reference} alt={item.reference_caption || "Immagine di riferimento"} />
          {item.reference_caption && <figcaption>{item.reference_caption}</figcaption>}
        </figure>
      )}

      <div className="videos">
        <VideoCard tag="A" src={item.video_A} />
        <VideoCard tag="B" src={item.video_B} />
      </div>

      <div className="questions">
        {QUESTIONS.map((q) => (
          <fieldset className="question" key={q.key}>
            <legend>{q.text}</legend>
            <div className="choices">
              {CHOICES.map((c) => {
                const selected = answers[q.key] === c.value;
                return (
                  <button
                    key={c.value}
                    type="button"
                    className={`choice${selected ? " selected" : ""}`}
                    onClick={() => setAnswer(q.key, c.value)}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>
          </fieldset>
        ))}
      </div>

      <div className="footer">
        <button
          type="button"
          className="submit"
          disabled={!allAnswered || submitting}
          onClick={submit}
        >
          {index + 1 < total ? "Prossimo confronto" : "Invia e concludi"}
        </button>
        {!allAnswered && <span className="hint">Rispondi a tutte le domande per continuare.</span>}
      </div>
    </Shell>
  );
}

function VideoCard({ tag, src }) {
  return (
    <div className="video-card">
      <div className="video-tag">Video {tag}</div>
      <video src={src} controls preload="metadata" playsInline />
    </div>
  );
}

function Shell({ children }) {
  return (
    <div className="page">
      <div className="container">{children}</div>
    </div>
  );
}
