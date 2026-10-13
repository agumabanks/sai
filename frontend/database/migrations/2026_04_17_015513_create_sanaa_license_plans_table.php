<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('sanaa_license_plans', function (Blueprint $table) {
            $table->uuid('id')->primary();
            $table->string('name');
            $table->integer('price_ugx');
            $table->integer('billing_cycle_days');
            $table->integer('max_members')->nullable();
            $table->integer('max_tellers')->nullable();
            $table->integer('max_loans_active')->nullable();
            $table->jsonb('features');
            $table->boolean('is_active')->default(true);
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('sanaa_license_plans');
    }
};
