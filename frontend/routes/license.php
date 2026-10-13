<?php

use App\Http\Controllers\Api\License\LicenseController;
use App\Http\Controllers\Api\License\PesaPalController;
use Illuminate\Support\Facades\Route;

Route::middleware('throttle:60,1')->prefix('api/license')->group(function () {
    Route::post('/check', [LicenseController::class, 'check']);
    Route::post('/ping', [LicenseController::class, 'ping']);
    Route::post('/pesapal/callback', [PesaPalController::class, 'callback']);
});
