<?php

// Filament handles all routes via AdminPanelProvider (path: /)

use App\Support\SanaaEcosystem;
use App\Support\SanaaOsFeatures;
use App\Support\SanaaOsPermissions;
use App\Support\SanaaSettings;
use App\Support\SanaaShell;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\Facades\Schema;

Route::get('/', function () {
    $path = public_path('os/index.html');
    abort_unless(is_file($path), 404);

    $html = file_get_contents($path);
    $token = csrf_token();
    $nonce = base64_encode(random_bytes(16));

    $html = str_replace(
        ['<meta name="csrf-token" content="">', '{{ csrf_token() }}'],
        '<meta name="csrf-token" content="'.$token.'">',
        $html,
    );

    // Harden script-src by replacing the static 'unsafe-inline' fallback with a per-request nonce.
    $html = str_replace(
        "script-src 'self' 'unsafe-inline' 'nonce-{{ csp_nonce }}'",
        "script-src 'self' 'nonce-".$nonce."'",
        $html,
    );

    return response($html, 200, ['Content-Type' => 'text/html; charset=UTF-8']);
})->name('sanaa.os');

Route::get('/os/csrf.json', fn () => response()->json(['token' => csrf_token()]))->name('sanaa.os.csrf');

Route::redirect('/os', '/');
Route::redirect('/os/', '/');

Route::redirect('/sanaa-doctor', '/admin/sanaa-doctor');
Route::redirect('/system-doctor', '/admin/system-doctor');

foreach (config('sanaa_os_features.features', []) as $feature) {
    if (($feature['type'] ?? '') !== 'filament' || empty($feature['path'])) {
        continue;
    }
    $slug = trim($feature['path'], '/');
    if ($slug === 'admin' || str_starts_with($slug, 'admin/')) {
        continue;
    }
    Route::redirect('/'.$slug, '/admin/'.$slug);
}

Route::get('/os/features.json', function () {
    return response()->json(SanaaOsFeatures::toJson());
})->name('sanaa.os.features');

Route::get('/os/shell.json', function () {
    return response()->json(SanaaShell::forJson());
})->name('sanaa.os.shell');

Route::get('/os/shell/live.json', function () {
    return response()->json(SanaaShell::liveData());
})->name('sanaa.os.shell.live');

Route::get('/os/doctor/overview.json', function () {
    return response()->json(SanaaEcosystem::overview());
})->name('sanaa.os.doctor.overview');

Route::get('/os/settings.json', function () {
    return response()->json(SanaaSettings::toJson());
})->name('sanaa.os.settings');

Route::get('/os/permissions.json', function () {
    return response()->json(SanaaOsPermissions::toJson());
})->name('sanaa.os.permissions');

Route::middleware('auth')->group(function () {
    Route::post('/os/ecosystem/poll', function () {
        return response()->json(SanaaEcosystem::pollAll());
    })->name('sanaa.os.ecosystem.poll');

    Route::post('/os/ecosystem/{appKey}/heal', function (string $appKey) {
        return response()->json(SanaaEcosystem::healApp($appKey));
    })->where('appKey', '[a-zA-Z0-9_.-]+')->name('sanaa.os.ecosystem.heal');
});

Route::get('/auth/status', function () {
    $user = auth()->user();

    if (! $user) {
        return response()->json(['authenticated' => false]);
    }

    return response()->json([
        'authenticated' => true,
        'email' => $user->email,
        'name' => $user->name,
        'role' => $user->role ?? 'operator',
        'primary_url' => url('/'),
        'os_url' => url('/'),
        'admin_url' => url('/admin'),
    ]);
})->name('sanaa.auth.status');

Route::post('/auth/os-bridge', function () {
    $user = auth()->user();
    if (! $user) {
        return response()->json(['authenticated' => false], 401);
    }

    $bridgeKey = (string) (config('sanaa_settings.engine_key') ?: env('SANAA_ENGINE_KEY', ''));
    if ($bridgeKey === '') {
        return response()->json(['authenticated' => false, 'error' => 'Bridge key not configured'], 500);
    }

    $payload = base64_encode(json_encode([
        'email' => $user->email,
        'role' => $user->role ?? 'operator',
        'name' => $user->name,
        'exp' => time() + 120,
    ], JSON_THROW_ON_ERROR));

    $signature = hash_hmac('sha256', $payload, $bridgeKey);

    return response()->json([
        'authenticated' => true,
        'token' => $payload.'.'.$signature,
    ]);
})->middleware('auth')->name('sanaa.auth.os-bridge');

Route::get('/media-intelligence/pdf/{filename}', function (string $filename) {
    abort_unless(auth()->check() || request()->hasValidSignature(), 403);

    $path = \App\Support\MediaIntelligencePdfs::pathForFilename($filename);
    abort_unless($path, 404);

    return response()->file($path, [
        'Content-Type' => 'application/pdf',
        'Content-Disposition' => 'inline; filename="'.basename($path).'"',
    ]);
})->where('filename', '[A-Za-z0-9_.-]+')->name('media-intelligence.pdf');

Route::get('/health', function () {
    $appKey = 'antigravity';
    $tenant = null;

    $queueDepth = Schema::hasTable('jobs') ? DB::table('jobs')->count() : 0;
    $failedJobs1h = Schema::hasTable('failed_jobs') ? DB::table('failed_jobs')->where('failed_at', '>=', now()->subHour())->count() : 0;

    $dbStart = microtime(true);
    DB::select('SELECT 1');
    $dbLatencyMs = round((microtime(true) - $dbStart) * 1000, 2);

    $redisOk = false;
    try {
        $redisOk = (bool) Redis::ping();
    } catch (\Exception $e) {
        $redisOk = false;
    }

    $errorRate1h = null;
    if (class_exists(\Laravel\Telescope\Telescope::class) && Schema::hasTable('telescope_entries')) {
        $errorRate1h = DB::table('telescope_entries')->where('type', 'exception')->where('created_at', '>=', now()->subHour())->count();
    } elseif (Schema::hasTable('logs')) {
        $errorRate1h = DB::table('logs')->where('level', 'error')->where('created_at', '>=', now()->subHour())->count();
    }

    $lastOrderAt = null;
    if (Schema::hasTable('orders')) {
        $lastOrder = DB::table('orders')->latest('created_at')->first();
        $lastOrderAt = $lastOrder?->created_at;
    }

    $activeSessions = null;
    if (Schema::hasTable('sessions')) {
        $activeSessions = DB::table('sessions')->where('last_activity', '>=', now()->subMinutes(15)->timestamp)->count();
    }

    $diskTotal = disk_total_space(storage_path());
    $diskFree = disk_free_space(storage_path());
    $diskFreePercent = $diskTotal > 0 ? round(($diskFree / $diskTotal) * 100, 2) : 0;
    $memoryUsedMb = round(memory_get_usage(true) / 1024 / 1024, 2);

    return response()->json([
        'app' => $appKey,
        'tenant' => $tenant,
        'timestamp' => now()->toIso8601String(),
        'version' => config('app.version', '1.0.0'),
        'signals' => [
            'queue_depth' => $queueDepth,
            'failed_jobs_1h' => $failedJobs1h,
            'db_latency_ms' => $dbLatencyMs,
            'redis_ok' => $redisOk,
            'error_rate_1h' => $errorRate1h,
            'last_order_at' => $lastOrderAt,
            'active_sessions' => $activeSessions,
            'disk_free_percent' => $diskFreePercent,
            'memory_used_mb' => $memoryUsedMb,
        ],
    ]);
})->middleware(\App\Http\Middleware\SanaaDoctorMiddleware::class);

Route::post('/health/heal', function (\Illuminate\Http\Request $request) {
    $appKey = 'antigravity';
    $tenant = null;

    $flags = $request->input('flags', []);
    $diagnosis = $request->input('diagnosis', '');
    $recommendedAction = $request->input('recommended_action', '');

    $actionsTaken = [];
    $healed = false;

    if (in_array('high queue depth', $flags, true)) {
        try {
            \Illuminate\Support\Facades\Artisan::call('queue:restart');
            $actionsTaken[] = 'queue:restart';
            $healed = true;
        } catch (\Exception $e) {
            $actionsTaken[] = 'queue:restart (failed)';
        }
    }

    if (in_array('high failed jobs', $flags, true)) {
        try {
            \Illuminate\Support\Facades\Artisan::call('queue:flush');
            \Illuminate\Support\Facades\Artisan::call('queue:restart');
            $actionsTaken[] = 'queue:flush + queue:restart';
            $healed = true;
        } catch (\Exception $e) {
            $actionsTaken[] = 'queue:flush + queue:restart (failed)';
        }
    }

    if (in_array('redis down', $flags, true)) {
        try {
            Redis::disconnect();
            Redis::connect();
            Redis::ping();
            $actionsTaken[] = 'redis:reconnected';
            $healed = true;
        } catch (\Exception $e) {
            $actionsTaken[] = 'redis:reconnect (failed)';
        }
    }

    if (in_array('manual_heal', $flags, true) && ! $healed) {
        try {
            \Illuminate\Support\Facades\Artisan::call('queue:restart');
            $actionsTaken[] = 'queue:restart (manual)';
            $healed = true;
        } catch (\Exception $e) {
            $actionsTaken[] = 'queue:restart (manual, failed)';
        }
    }

    if (Schema::hasTable('sanaa_heal_log')) {
        DB::table('sanaa_heal_log')->insert([
            'app' => $appKey,
            'tenant' => $tenant,
            'flags' => json_encode($flags),
            'diagnosis' => $diagnosis,
            'recommended_action' => $recommendedAction,
            'actions_taken' => json_encode($actionsTaken),
            'healed' => $healed,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
    }

    return response()->json(['healed' => $healed, 'actions_taken' => $actionsTaken]);
})->middleware(\App\Http\Middleware\SanaaDoctorMiddleware::class);
