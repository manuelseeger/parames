import { createApp, computed, h } from 'vue';
import { route, match } from './router.js';
import { Dashboard } from './views/Dashboard.js';
import { AlertDefinitionsList } from './views/AlertDefinitionsList.js';
import { AlertDefinitionForm } from './views/AlertDefinitionForm.js';

const Shell = {
  setup() {
    const view = computed(() => {
      const path = route.value;
      if (path === '/' || path === '') return { component: Dashboard };
      if (path === '/alerts') return { component: AlertDefinitionsList };
      if (path === '/alerts/new') return { component: AlertDefinitionForm, props: { id: null } };
      const m = match('/alerts/:id', path);
      if (m) return { component: AlertDefinitionForm, props: { id: m.id } };
      return { component: { template: '<div class="card">Not found: <code>{{ path }}</code></div>', data() { return { path }; } } };
    });

    function isActive(prefix) {
      if (prefix === '/') return route.value === '/' || route.value === '';
      return route.value.startsWith(prefix);
    }

    return { view, isActive };
  },
  render() {
    return h('div', { class: 'app' }, [
      h('nav', { class: 'nav' }, [
        h('span', { class: 'brand' }, 'Parames'),
        h('a', { href: '#/', class: { active: this.isActive('/') } }, 'Dashboard'),
        h('a', { href: '#/alerts', class: { active: this.isActive('/alerts') } }, 'Alert definitions'),
        h('span', { class: 'spacer' }),
        h('a', { href: '/api/docs', target: '_blank', class: 'muted' }, 'API docs'),
      ]),
      h(this.view.component, this.view.props || {}),
    ]);
  },
};

createApp(Shell).mount('#app');
