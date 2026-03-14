---
name: frontend-worker
description: PHP Laravel/Filament frontend worker for pages, widgets, components, services, and tests
---

# Frontend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Use for any feature that modifies the Laravel/Filament frontend:
- New Filament pages (app/Filament/Pages/)
- Modified Filament pages and widgets
- New Livewire components (app/Livewire/)
- Service classes for backend API integration (app/Services/)
- Blade views and templates (resources/views/)
- Models and migrations (app/Models/, database/migrations/)
- Auth, RBAC, and user management changes
- Frontend tests (tests/Feature/, tests/Unit/)
- CSS/styling changes (resources/css/)

## Work Procedure

### 1. Understand the Feature
- Read the feature description, preconditions, expectedBehavior, and verificationSteps carefully
- Read AGENTS.md for mission boundaries and coding conventions
- Read relevant existing code to understand patterns. Key files:
  - `frontend/app/Filament/Pages/` — existing Filament pages for pattern reference
  - `frontend/app/Services/SanaaEngineService.php` — backend API client
  - `frontend/app/Livewire/SanaaTerminal.php` — main chat component
  - `frontend/resources/css/app.css` — custom theme and glass utilities
  - `frontend/app/Providers/Filament/AdminPanelProvider.php` — panel configuration
- Check `.factory/library/` for relevant knowledge
- Look at an existing page (e.g., SkillsCommandCenter.php) to match style

### 2. Write Tests FIRST (Red Phase)
- Create test file in `frontend/tests/Feature/` following Laravel conventions
- Write tests that cover: page loads without errors, displays expected content, forms submit correctly
- For Livewire: test component rendering, method calls, state changes
- Run tests to confirm they FAIL: `cd /var/www/ai.sanaa.co/frontend && php artisan test --filter={TestClass}`
- Tests MUST fail before implementation begins

### 3. Implement the Feature (Green Phase)
- **Filament pages:** Create page class extending `Filament\Pages\Page`
  - Set `$navigationIcon`, `$navigationGroup`, `$navigationLabel`
  - Use `HasPageShield` trait if RBAC is implemented
  - Create Blade view in `resources/views/filament/pages/`
- **API integration:** Add methods to `SanaaEngineService` for new backend endpoints
  - Use `$this->get()`, `$this->post()`, `$this->put()`, `$this->delete()` methods
  - Handle errors with try/catch and Filament notifications
- **Styling:** Follow glassmorphic dark theme
  - Use `.glass`, `.glass-dark`, `.glass-light` for containers
  - Use `bg-sanaa-obsidian` for backgrounds
  - Use gradient classes for accent elements
  - Follow existing MetricCard pattern for stats
  - Use Heroicons (`heroicon-o-*`) for all icons
- **Livewire:** For interactive components
  - Public properties for state
  - Wire methods for actions
  - Polling for live data (use `$pollingInterval` or `wire:poll`)

### 4. Make Tests Pass
- Run feature tests: `cd /var/www/ai.sanaa.co/frontend && php artisan test --filter={TestClass}`
- Fix implementation until all tests pass
- Run full test suite: `cd /var/www/ai.sanaa.co/frontend && php artisan test`
- Check for PHP syntax errors: `php -l app/Filament/Pages/{NewPage}.php`

### 5. Manual Verification
- Restart PHP if needed: `sudo systemctl restart php8.4-fpm`
- Clear Laravel caches: `cd /var/www/ai.sanaa.co/frontend && php artisan optimize:clear`
- Verify the page is registered by checking route list: `php artisan route:list | grep {page-slug}`
- Check Laravel logs for errors: `tail -20 /var/www/ai.sanaa.co/frontend/storage/logs/laravel.log`

### 6. Cleanup
- Clear compiled views: `php artisan view:clear`
- Ensure no orphaned processes

## Example Handoff

```json
{
  "salientSummary": "Implemented TenantControl Filament page with backend API integration showing all managed tenants (finance, soko, mailcow) with health scores and status badges. Wrote 4 PHPUnit tests (all passing). Page loads at /tenant-control with proper navigation group.",
  "whatWasImplemented": "Created app/Filament/Pages/TenantControl.php with glassmorphic card layout showing tenant grid. Added getTenants(), getTenantHealth() methods to SanaaEngineService. Created Blade view at resources/views/filament/pages/tenant-control.blade.php with MetricCard components per tenant, status badges (active/inactive/degraded), health scores, and last-checked timestamps. Registered in Infrastructure navigation group with heroicon-o-server-stack icon.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "cd /var/www/ai.sanaa.co/frontend && php artisan test --filter=TenantControlTest",
        "exitCode": 0,
        "observation": "4 tests passed: test_page_loads, test_displays_tenant_cards, test_shows_health_scores, test_navigation_registered"
      },
      {
        "command": "cd /var/www/ai.sanaa.co/frontend && php artisan test",
        "exitCode": 0,
        "observation": "Full suite: 11 tests, 11 passed"
      },
      {
        "command": "php -l /var/www/ai.sanaa.co/frontend/app/Filament/Pages/TenantControl.php",
        "exitCode": 0,
        "observation": "No syntax errors detected"
      },
      {
        "command": "cd /var/www/ai.sanaa.co/frontend && php artisan route:list | grep tenant",
        "exitCode": 0,
        "observation": "GET /tenant-control route registered"
      }
    ],
    "interactiveChecks": [
      {
        "action": "Checked laravel.log for errors after page registration",
        "observed": "No new errors in log file related to TenantControl"
      }
    ]
  },
  "tests": {
    "added": [
      {
        "file": "frontend/tests/Feature/TenantControlTest.php",
        "cases": [
          { "name": "test_page_loads", "verifies": "Page returns 200 and renders without errors" },
          { "name": "test_displays_tenant_cards", "verifies": "Page shows tenant name and type for each registered tenant" },
          { "name": "test_shows_health_scores", "verifies": "Health score values are displayed per tenant" },
          { "name": "test_navigation_registered", "verifies": "Page appears in Infrastructure navigation group" }
        ]
      }
    ]
  },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Backend API endpoint that the page needs doesn't exist yet
- SanaaEngineService is missing a method needed for this feature
- Filament panel provider configuration needs changes that affect other pages
- PHP version incompatibility with a required package
- Cannot restart php8.4-fpm or nginx (service won't come up)
- Existing tests fail after changes (regression)
