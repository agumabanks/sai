<?php

namespace App\Services;

use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

class TenantProvisioningRunService
{
    private const DISK = 'local';

    private const DIRECTORY = 'tenant-provisioning-runs';

    public function create(array $args, array $meta = []): array
    {
        $runId = (string) Str::uuid();
        $domain = (string) ($meta['domain'] ?? $args['domain'] ?? 'tenant');

        $state = [
            'id' => $runId,
            'status' => 'queued',
            'created_at' => now()->toIso8601String(),
            'updated_at' => now()->toIso8601String(),
            'started_at' => null,
            'finished_at' => null,
            'output' => "Queued provisioning for {$domain}.\nThe run is continuing in the background. This page will update automatically.",
            'error' => '',
            'data' => [
                'domain' => $domain,
                'url' => $meta['url'] ?? null,
            ],
            'meta' => $meta,
            'args_encrypted' => Crypt::encryptString(json_encode($args, JSON_THROW_ON_ERROR)),
        ];

        $this->saveRaw($state);

        return $this->publicState($state);
    }

    public function get(string $runId): ?array
    {
        $state = $this->loadRaw($runId);

        return $state ? $this->publicState($state) : null;
    }

    public function getArgs(string $runId): array
    {
        $state = $this->loadRaw($runId);

        if (! $state || empty($state['args_encrypted'])) {
            return [];
        }

        $decoded = json_decode(Crypt::decryptString((string) $state['args_encrypted']), true);

        return is_array($decoded) ? $decoded : [];
    }

    public function markRunning(string $runId): void
    {
        $state = $this->loadRaw($runId);

        if (! $state) {
            return;
        }

        $state['status'] = 'running';
        $state['started_at'] = $state['started_at'] ?? now()->toIso8601String();
        $state['updated_at'] = now()->toIso8601String();
        $state['output'] = trim(((string) ($state['output'] ?? ''))."\n\nProvisioning is running in the background.");

        $this->saveRaw($state);
    }

    public function complete(string $runId, array $result): void
    {
        $state = $this->loadRaw($runId);

        if (! $state) {
            return;
        }

        $success = (bool) ($result['success'] ?? false);

        $state['status'] = $success ? 'succeeded' : 'failed';
        $state['finished_at'] = now()->toIso8601String();
        $state['updated_at'] = now()->toIso8601String();
        $state['output'] = (string) ($result['output'] ?? ($state['output'] ?? ''));
        $state['error'] = (string) ($result['error'] ?? '');
        $state['data'] = array_merge(
            is_array($state['data'] ?? null) ? $state['data'] : [],
            is_array($result['data'] ?? null) ? $result['data'] : []
        );

        $this->saveRaw($state);
    }

    public function fail(string $runId, string $error): void
    {
        $state = $this->loadRaw($runId);

        if (! $state) {
            return;
        }

        $state['status'] = 'failed';
        $state['finished_at'] = now()->toIso8601String();
        $state['updated_at'] = now()->toIso8601String();
        $state['error'] = $error;
        $state['output'] = trim(((string) ($state['output'] ?? ''))."\n\nERROR: {$error}");

        $this->saveRaw($state);
    }

    private function loadRaw(string $runId): ?array
    {
        $path = $this->path($runId);

        if (! Storage::disk(self::DISK)->exists($path)) {
            return null;
        }

        $decoded = json_decode((string) Storage::disk(self::DISK)->get($path), true);

        return is_array($decoded) ? $decoded : null;
    }

    private function saveRaw(array $state): void
    {
        Storage::disk(self::DISK)->put(
            $this->path((string) $state['id']),
            json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
        );
    }

    private function publicState(array $state): array
    {
        unset($state['args_encrypted']);

        return $state;
    }

    private function path(string $runId): string
    {
        return self::DIRECTORY.'/'.$runId.'.json';
    }
}
