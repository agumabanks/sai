<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('sanaa_license_events', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->foreignUuid('tenant_id')->constrained('sanaa_license_tenants');
            $table->enum('event_type', ['checked', 'warned', 'suspended', 'reactivated', 'killed', 'payment_recorded', 'plan_changed']);
            $table->enum('triggered_by', ['system', 'admin', 'api']);
            $table->jsonb('payload')->nullable();
            $table->timestamp('created_at')->useCurrent();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('sanaa_license_events');
    }
};
