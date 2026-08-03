import { useState } from 'react';

function TaskRow({ task, onToggle, onRemove }) {
  return (
    <li className={task.done ? 'task done' : 'task'}>
      <label>
        <input type="checkbox" checked={task.done} onChange={() => onToggle(task.id)} />
        <span>{task.text}</span>
      </label>
      <button className="remove" onClick={() => onRemove(task.id)} aria-label={`Remove ${task.text}`}>
        ×
      </button>
    </li>
  );
}

export default function App() {
  const [tasks, setTasks] = useState([
    { id: 1, text: 'Edit src/App.jsx to make it yours', done: false },
    { id: 2, text: 'Run npm install && npm run dev', done: true },
  ]);
  const [draft, setDraft] = useState('');

  const addTask = (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setTasks((prev) => [...prev, { id: Date.now(), text, done: false }]);
    setDraft('');
  };

  const toggle = (id) =>
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));
  const remove = (id) => setTasks((prev) => prev.filter((t) => t.id !== id));

  const remaining = tasks.filter((t) => !t.done).length;

  return (
    <main className="app">
      <h1>Acme Tasks</h1>
      <p className="sub">
        {remaining} of {tasks.length} remaining
      </p>

      <form onSubmit={addTask} className="add">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a task…"
          aria-label="New task"
        />
        <button type="submit">Add</button>
      </form>

      <ul className="tasks">
        {tasks.map((t) => (
          <TaskRow key={t.id} task={t} onToggle={toggle} onRemove={remove} />
        ))}
      </ul>
    </main>
  );
}
