<script setup>
import { ref, watch } from 'vue';

const props = defineProps({
  mode: { type: String, required: true },
  error: { type: String, default: '' },
  submitting: { type: Boolean, default: false },
});
const emit = defineEmits(['submit']);
const email = ref('');
const password = ref('');
watch(() => props.mode, () => { password.value = ''; });

function submit() {
  emit('submit', { mode: props.mode, email: email.value.trim(), password: password.value });
}
</script>

<template>
  <form class="card auth-card" @submit.prevent="submit">
    <h1>Parames</h1>
    <h2>{{ mode === 'signup' ? 'Create account' : 'Log in' }}</h2>
    <div v-if="error" class="error" role="alert">{{ error }}</div>
    <div class="field">
      <label for="auth-email">Email</label>
      <input id="auth-email" v-model="email" type="email" autocomplete="email" required autofocus>
    </div>
    <div class="field">
      <label for="auth-password">Password</label>
      <input id="auth-password" v-model="password" type="password" :autocomplete="mode === 'signup' ? 'new-password' : 'current-password'" required>
    </div>
    <button class="btn btn-primary" type="submit" :disabled="submitting">{{ submitting ? 'Please wait…' : mode === 'signup' ? 'Sign up' : 'Log in' }}</button>
    <p v-if="mode === 'signup'">Have an account? <a href="#/login">Log in</a></p>
    <p v-else>Need an account? <a href="#/signup">Sign up</a></p>
  </form>
</template>
