<?php

namespace Tests\Feature;

use App\Filament\Pages\Auth\Login;
use Livewire\Livewire;
use Tests\TestCase;

class LoginErrorTest extends TestCase
{
    public function test_login_submit_error()
    {
        Livewire::test(Login::class)
            ->set('data.email', 'admin@sanaa.co')
            ->set('data.password', 'password')
            ->call('authenticate')
            ->assertHasNoErrors();
    }
}
