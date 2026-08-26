<script setup>
import { onMounted, ref } from 'vue'
import { createItem, deleteItem, listItems } from './api'

const items = ref([])
const name = ref('')
const description = ref('')
const error = ref('')

async function refresh() {
  try {
    items.value = await listItems()
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}

async function addItem() {
  if (!name.value.trim()) return
  await createItem({ name: name.value, description: description.value || null })
  name.value = ''
  description.value = ''
  await refresh()
}

async function removeItem(id) {
  await deleteItem(id)
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <main>
    <h1>math-high</h1>
    <p class="subtitle">Vue + FastAPI + SQLite starter</p>

    <form @submit.prevent="addItem">
      <input v-model="name" placeholder="Item name" required />
      <input v-model="description" placeholder="Description (optional)" />
      <button type="submit">Add</button>
    </form>

    <p v-if="error" class="error">{{ error }}</p>

    <ul>
      <li v-for="item in items" :key="item.id">
        <strong>{{ item.name }}</strong>
        <span v-if="item.description"> — {{ item.description }}</span>
        <button @click="removeItem(item.id)">Delete</button>
      </li>
    </ul>
    <p v-if="!items.length && !error">No items yet.</p>
  </main>
</template>

<style scoped>
main {
  max-width: 560px;
  margin: 3rem auto;
  padding: 0 1rem;
  font-family: system-ui, sans-serif;
}
.subtitle {
  color: #666;
  margin-top: -0.5rem;
}
form {
  display: flex;
  gap: 0.5rem;
  margin: 1.5rem 0;
}
input {
  flex: 1;
  padding: 0.4rem;
}
button {
  padding: 0.4rem 0.8rem;
}
ul {
  list-style: none;
  padding: 0;
}
li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid #eee;
}
li button {
  margin-left: auto;
}
.error {
  color: #c00;
}
</style>
