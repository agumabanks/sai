<?php

namespace App\Providers;

use App\Filament\Pages\Auth\Login;
use Illuminate\Support\ServiceProvider;
use Livewire\Livewire;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        //
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        // Keep the legacy Filament alias alive for login pages that were opened
        // before the custom login component name was deployed.
        Livewire::component('auth.login', Login::class);
        Livewire::component('app.filament.pages.auth.login', Login::class);
    }
}
