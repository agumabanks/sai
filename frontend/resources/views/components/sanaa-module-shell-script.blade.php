@props(['modules'])

<script>
(() => {
    const modules = @js(array_values($modules));
    const shell = window.SanaaModuleShell = window.SanaaModuleShell || {};

    shell.modules = modules;
    shell.storageKey = 'sanaa_active_module';
    shell.find = (id) => shell.modules.find((module) => module.id === id);
    shell.fallback = () => shell.modules[0];
    shell.normalizePath = (value) => {
        try {
            const path = new URL(value, window.location.origin).pathname.replace(/\/+$/, '');
            return path === '' ? '/' : path;
        } catch (error) {
            const path = String(value || '/').replace(/\/+$/, '');
            return path === '' ? '/' : path;
        }
    };
    shell.pathMatches = (target, path) => {
        const cleanTarget = shell.normalizePath(target);
        const cleanPath = shell.normalizePath(path);

        return cleanTarget === '/'
            ? cleanPath === '/'
            : cleanPath === cleanTarget || cleanPath.startsWith(`${cleanTarget}/`);
    };
    shell.inferActive = () => {
        const currentPath = shell.normalizePath(window.location.pathname);

        return shell.modules.find((module) => {
            return (module.paths || []).some((path) => shell.pathMatches(path, currentPath));
        })?.id || null;
    };
    shell.remember = (id) => {
        if (! shell.find(id)) {
            return;
        }

        window.localStorage.setItem(shell.storageKey, id);
    };
    shell.active = () => {
        const inferred = shell.inferActive();

        if (inferred) {
            shell.remember(inferred);
            return inferred;
        }

        const stored = window.localStorage.getItem(shell.storageKey);

        return shell.find(stored)?.id || shell.fallback()?.id || 'overview';
    };
    shell.setActive = (id, options = {}) => {
        const module = shell.find(id);

        if (! module) {
            return;
        }

        shell.remember(module.id);
        window.dispatchEvent(new CustomEvent('sanaa-module-changed', {
            detail: { id: module.id, module },
        }));

        if (options.navigate === false || ! module.url) {
            return;
        }

        if (shell.normalizePath(window.location.href) !== shell.normalizePath(module.url)) {
            window.location.href = module.url;
        }
    };

    const registerAlpine = () => {
        if (! window.Alpine || shell.alpineRegistered) {
            return;
        }

        shell.alpineRegistered = true;

        Alpine.data('sanaaAppLauncher', () => ({
            open: false,
            activeModuleId: shell.active(),
            panelLeft: 12,
            panelTop: 58,
            get activeModule() {
                return shell.find(this.activeModuleId) || shell.fallback();
            },
            init() {
                this.syncFromRoute();

                window.addEventListener('sanaa-module-changed', (event) => {
                    this.activeModuleId = event.detail.id;
                });

                document.addEventListener('livewire:navigated', () => this.syncFromRoute());
            },
            syncFromRoute() {
                this.activeModuleId = shell.active();
            },
            moduleIsActive(id) {
                return this.activeModuleId === id;
            },
            toggle() {
                this.open = ! this.open;

                if (this.open) {
                    this.$nextTick(() => this.positionPanel());
                }
            },
            positionPanel() {
                const trigger = this.$refs.trigger;

                if (! trigger) {
                    return;
                }

                const rect = trigger.getBoundingClientRect();
                const margin = window.innerWidth < 520 ? 8 : 12;
                const panelWidth = Math.min(352, window.innerWidth - (margin * 2));
                const maxLeft = Math.max(margin, window.innerWidth - panelWidth - margin);
                const panel = this.$refs.panel;
                const measuredHeight = panel?.offsetHeight || 460;
                const panelHeight = Math.min(measuredHeight, window.innerHeight - (margin * 2));
                const preferredTop = rect.bottom + 10;
                const maxTop = Math.max(margin, window.innerHeight - panelHeight - margin);

                this.panelLeft = Math.min(Math.max(margin, rect.right - panelWidth), maxLeft);
                this.panelTop = Math.min(Math.max(margin, preferredTop), maxTop);
            },
            selectModule(id, navigate = true) {
                this.activeModuleId = id;
                this.open = false;
                shell.setActive(id, { navigate });
            },
        }));

        Alpine.data('sanaaSidebarModuleMenu', () => ({
            activeModuleId: shell.active(),
            observer: null,
            get activeModule() {
                return shell.find(this.activeModuleId) || shell.fallback();
            },
            init() {
                this.syncAndFilter();

                window.addEventListener('sanaa-module-changed', (event) => {
                    this.activeModuleId = event.detail.id;
                    this.applyFilter();
                });

                document.addEventListener('livewire:navigated', () => {
                    window.setTimeout(() => this.syncAndFilter(), 80);
                });

                this.$nextTick(() => {
                    const nav = document.querySelector('.fi-sidebar-nav-groups');

                    if (! nav || this.observer) {
                        return;
                    }

                    this.observer = new MutationObserver(() => this.applyFilter());
                    this.observer.observe(nav, { childList: true, subtree: true });
                });
            },
            syncAndFilter() {
                this.activeModuleId = shell.active();
                this.applyFilter();
            },
            applyFilter() {
                const module = shell.find(this.activeModuleId) || shell.fallback();
                const allowedGroups = (module.groups || []).map((group) => String(group).trim().toLowerCase());
                const sidebar = document.querySelector('.fi-sidebar');

                if (sidebar) {
                    sidebar.dataset.sanaaActiveModule = module.id;
                }

                document.querySelectorAll('.fi-sidebar-group').forEach((group) => {
                    const label = String(group.dataset.groupLabel || '').trim().toLowerCase();
                    const visible = allowedGroups.includes(label);

                    group.dataset.sanaaVisible = visible ? 'true' : 'false';
                    group.style.display = visible ? '' : 'none';
                });
            },
        }));
    };

    registerAlpine();
    document.addEventListener('alpine:init', registerAlpine);
})();
</script>
