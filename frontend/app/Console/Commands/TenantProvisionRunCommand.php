<?php

namespace App\Console\Commands;

use App\Services\SanaaEngineService;
use App\Services\TenantProvisioningRunService;
use Illuminate\Console\Command;
use Throwable;

class TenantProvisionRunCommand extends Command
{
    protected $signature = 'tenant:provision-run {runId}';

    protected $description = 'Execute a tenant provisioning run in the background';

    public function handle(TenantProvisioningRunService $runs, SanaaEngineService $engine): int
    {
        $runId = (string) $this->argument('runId');
        $args = $runs->getArgs($runId);

        if ($args === []) {
            $runs->fail($runId, 'Provision run payload was not found.');

            return self::FAILURE;
        }

        $runs->markRunning($runId);

        try {
            $result = $engine->runSkill(
                'tenant_provisioning',
                $args,
                'admin:tenant_provisioning',
                900
            );

            $runs->complete($runId, $result);

            return ($result['success'] ?? false) ? self::SUCCESS : self::FAILURE;
        } catch (Throwable $e) {
            report($e);
            $runs->fail($runId, $e->getMessage());

            return self::FAILURE;
        }
    }
}
