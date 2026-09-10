
const express = require('express');
const path = require('path');
const cors = require('cors');
const app = express();

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// In-memory databases for testing
let posts = [
  { id: 1, user: 'Anonymous_27', role: 'user', time: '2 hours ago', text: "Sometimes I feel like no one understands what I'm going through, but writing it down here makes me feel a little lighter. 💜", likes: 24, mood: { name: 'Loved', emoji: '❤️' } },
  { id: 2, user: 'Admin_Sarah', role: 'admin', time: '5 hours ago', text: "Welcome everyone to Mindora! Remember to treat each other with kindness. We are so glad you are here. 🌱", likes: 89, mood: { name: 'Happy', emoji: '😄' } },
  { id: 3, user: 'Anonymous_45', role: 'user', time: '1 day ago', text: "Grateful for the little things today. Let's all take care of ourselves. ✨", likes: 21, mood: { name: 'Good', emoji: '😊' } }
];

let staffInbox = [
  { id: 1, sender: 'Anonymous_88', type: 'Report Issue', text: 'Someone is spamming links in the feed.' }
];

// --- Feed API ---
app.get('/api/posts', (req, res) => res.json(posts));

app.post('/api/posts', (req, res) => {
  const newPost = { id: Date.now(), ...req.body, likes: 0, time: 'Just now' };
  posts.unshift(newPost);
  res.json(newPost);
});

app.delete('/api/posts/:id', (req, res) => {
  posts = posts.filter(p => p.id !== parseInt(req.params.id));
  res.json({ success: true });
});

app.put('/api/posts/:id/like', (req, res) => {
  const post = posts.find(p => p.id === parseInt(req.params.id));
  if (post) post.likes += req.body.increment ? 1 : -1;
  res.json(post);
});

// --- Contact & Inbox API ---
// --- Chat & Staff Inbox API ---

let messages = [];

// Get messages for ONE user
app.get('/api/chat/:userId', (req, res) => {
  const userId = req.params.userId;

  const userMessages = messages.filter(
    message => message.userId === userId
  );

  res.json(userMessages);
});

// User sends a message
app.post('/api/chat/:userId', (req, res) => {
  const userId = req.params.userId;
  const { text } = req.body;

  if (!text || !text.trim()) {
    return res.status(400).json({
      message: 'Message cannot be empty.'
    });
  }

  const message = {
    id: Date.now(),
    userId: userId,
    sender: 'user',
    text: text.trim(),
    time: new Date().toISOString(),
    read: false
  };

  messages.push(message);

  res.json(message);
});

// Staff gets ALL conversations
app.get('/api/staff/chats', (req, res) => {
  res.json(messages);
});

// Staff replies to a specific user
app.post('/api/staff/chat/:userId', (req, res) => {
  const userId = req.params.userId;
  const { text } = req.body;

  if (!text || !text.trim()) {
    return res.status(400).json({
      message: 'Message cannot be empty.'
    });
  }

  const message = {
    id: Date.now(),
    userId: userId,
    sender: 'staff',
    text: text.trim(),
    time: new Date().toISOString(),
    read: false
  };

  messages.push(message);

  res.json(message);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Mindora backend running on port ${PORT}`));
