-- Tarantool initialization script
-- Creates spaces for cache, reports, and threads with proper indexing

box.cfg {
    listen = 3302,
    log_level = 5,
}

-- ============================================================================
-- SPACE 1: CACHE
-- Temporary data with TTL for API responses
-- ============================================================================

box.schema.space.create('cache', {if_not_exists = true})

box.space.cache:format({
    {name = 'key', type = 'string'},
    {name = 'value', type = 'any'},
    {name = 'ttl', type = 'number'},
    {name = 'created_at', type = 'number'},
    {name = 'source', type = 'string'}  -- для статистики по источникам
})

-- Primary index by key
box.space.cache:create_index('primary', {
    parts = {'key'},
    if_not_exists = true
})

-- Secondary index by TTL for efficient cleanup
box.space.cache:create_index('ttl_idx', {
    parts = {'ttl'},
    if_not_exists = true,
    unique = false
})

-- Secondary index by source for statistics
box.space.cache:create_index('source_idx', {
    parts = {'source'},
    if_not_exists = true,
    unique = false
})

print('✓ Cache space created with indexes')

-- ============================================================================
-- SPACE 2: REPORTS
-- Client analysis reports with 30-day TTL
-- ============================================================================

box.schema.space.create('reports', {if_not_exists = true})

box.space.reports:format({
    {name = 'report_id', type = 'string'},
    {name = 'inn', type = 'string'},
    {name = 'client_name', type = 'string'},
    {name = 'report_data', type = 'any'},
    {name = 'created_at', type = 'number'},
    {name = 'expires_at', type = 'number'},
    {name = 'risk_level', type = 'string'},
    {name = 'risk_score', type = 'number'}
})

-- Primary index by report_id
box.space.reports:create_index('primary', {
    parts = {'report_id'},
    if_not_exists = true
})

-- Secondary index by INN for quick lookup
box.space.reports:create_index('inn_idx', {
    parts = {'inn'},
    if_not_exists = true,
    unique = false
})

-- Secondary index by expiration for cleanup
box.space.reports:create_index('expires_idx', {
    parts = {'expires_at'},
    if_not_exists = true,
    unique = false
})

-- Secondary index by creation date for listing
box.space.reports:create_index('created_idx', {
    parts = {'created_at'},
    if_not_exists = true,
    unique = false
})

-- Secondary index by risk level for filtering
box.space.reports:create_index('risk_idx', {
    parts = {'risk_level'},
    if_not_exists = true,
    unique = false
})

print('✓ Reports space created with indexes')

-- ============================================================================
-- SPACE 3: THREADS
-- Conversation/analysis history (no TTL, persistent)
-- ============================================================================

box.schema.space.create('threads', {if_not_exists = true})

box.space.threads:format({
    {name = 'thread_id', type = 'string'},
    {name = 'thread_data', type = 'any'},
    {name = 'created_at', type = 'number'},
    {name = 'updated_at', type = 'number'},
    {name = 'client_name', type = 'string'},
    {name = 'inn', type = 'string'}
})

-- Primary index by thread_id
box.space.threads:create_index('primary', {
    parts = {'thread_id'},
    if_not_exists = true
})

-- Secondary index by creation date for listing (newest first)
box.space.threads:create_index('created_idx', {
    parts = {'created_at'},
    if_not_exists = true,
    unique = false
})

-- Secondary index by INN for filtering
box.space.threads:create_index('inn_idx', {
    parts = {'inn'},
    if_not_exists = true,
    unique = false
})

-- Secondary index by client_name for search
box.space.threads:create_index('client_idx', {
    parts = {'client_name'},
    if_not_exists = true,
    unique = false
})

print('✓ Threads space created with indexes')

-- ============================================================================
-- SPACE 4: PERSISTENT (legacy, for backward compatibility)
-- Will be gradually deprecated in favor of specific spaces
-- ============================================================================

box.schema.space.create('persistent', {if_not_exists = true})

box.space.persistent:format({
    {name = 'key', type = 'string'},
    {name = 'value', type = 'any'}
})

box.space.persistent:create_index('primary', {
    parts = {'key'},
    if_not_exists = true
})

print('✓ Persistent space created (legacy)')

-- ============================================================================
-- CLEANUP FUNCTIONS
-- ============================================================================

function cleanup_expired()
    local now = os.time()
    local cleaned_cache = 0
    local cleaned_reports = 0
    
    -- Cleanup expired cache entries
    -- Оптимизация: используем ttl_idx (вместо полного скана)
    for _, tuple in box.space.cache.index.ttl_idx:pairs(now, {iterator = 'LE'}) do
        if tuple.ttl and tuple.ttl < now then
            box.space.cache:delete(tuple.key)
            cleaned_cache = cleaned_cache + 1
        end
    end
    
    -- Cleanup expired reports (30 days old)
    -- Оптимизация: используем expires_idx (вместо полного скана)
    for _, tuple in box.space.reports.index.expires_idx:pairs(now, {iterator = 'LE'}) do
        if tuple.expires_at and tuple.expires_at < now then
            box.space.reports:delete(tuple.report_id)
            cleaned_reports = cleaned_reports + 1
        end
    end
    
    return {
        cleaned_cache = cleaned_cache,
        cleaned_reports = cleaned_reports,
        timestamp = now
    }
end

function get_space_stats()
    return {
        cache = box.space.cache:len(),
        reports = box.space.reports:len(),
        threads = box.space.threads:len(),
        persistent = box.space.persistent:len()
    }
end

function get_reports_by_inn(inn)
    local results = {}
    for _, tuple in box.space.reports.index.inn_idx:pairs(inn) do
        table.insert(results, {
            report_id = tuple.report_id,
            client_name = tuple.client_name,
            created_at = tuple.created_at,
            risk_level = tuple.risk_level,
            risk_score = tuple.risk_score
        })
    end
    return results
end

-- ============================================================================
-- CACHE HELPERS (для ускорения dashboard/maintenance операций)
-- ============================================================================

-- Быстрое получение количества записей в кеше (без скана)
function cache_len()
    return box.space.cache:len()
end

-- Быстро очистить весь кеш (truncate по space)
function cache_clear()
    box.space.cache:truncate()
    return true
end

-- Удаление ключей по префиксу через primary index iterator=GE.
-- Это существенно быстрее полного скана для большинства префиксов.
function cache_delete_by_prefix(prefix)
    if prefix == nil or prefix == '' then
        return {deleted = 0, error = 'prefix_required'}
    end

    local deleted = 0

    -- Итерируемся от prefix и останавливаемся, когда ключи перестают начинаться с prefix.
    for _, tuple in box.space.cache.index.primary:pairs(prefix, {iterator = 'GE'}) do
        local k = tuple.key
        if k == nil then
            break
        end
        if string.sub(k, 1, string.len(prefix)) ~= prefix then
            break
        end
        box.space.cache:delete(k)
        deleted = deleted + 1
    end

    return {deleted = deleted}
end

-- Получение первых N ключей кеша для UI. Возвращаем метаданные, не пытаясь декодировать value.
function cache_get_entries(limit)
    local lim = tonumber(limit) or 10
    if lim < 1 then lim = 1 end
    if lim > 500 then lim = 500 end

    local now = os.time()
    local entries = {}
    local i = 0

    for _, tuple in box.space.cache.index.primary:pairs(nil, {iterator = 'ALL'}) do
        if i >= lim then break end
        local ttl = tuple.ttl or 0
        if ttl >= now then
            local size_bytes = 0
            if type(tuple.value) == 'string' then
                size_bytes = string.len(tuple.value)
            end
            table.insert(entries, {
                key = tuple.key,
                expires_in = math.max(0, ttl - now),
                size_bytes = size_bytes,
                source = tuple.source,
                created_at = tuple.created_at
            })
            i = i + 1
        end
    end

    return entries
end

-- ============================================================================
-- MIGRATION FUNCTION
-- Migrate old persistent threads to new threads space
-- ============================================================================

function migrate_persistent_to_threads()
    if box.space.persistent == nil then
        print('No persistent space to migrate')
        return 0
    end
    
    local migrated = 0
    local errors = 0
    
    for _, tuple in box.space.persistent:pairs() do
        local key = tuple.key
        
        -- Only migrate thread: keys
        if key and key:match("^thread:") then
            local thread_id = key:gsub("^thread:", "")
            local data = tuple.value
            
            if data then
                local ok, err = pcall(function()
                    -- Check if already exists in threads
                    local existing = box.space.threads:get(thread_id)
                    if not existing then
                        box.space.threads:insert({
                            thread_id,
                            data,
                            data.created_at or os.time(),
                            os.time(),
                            data.client_name or '',
                            data.inn or ''
                        })
                        migrated = migrated + 1
                    end
                end)
                
                if not ok then
                    errors = errors + 1
                    print('Migration error for ' .. thread_id .. ': ' .. tostring(err))
                end
            end
        end
    end
    
    print(string.format('Migration completed: %d migrated, %d errors', migrated, errors))
    return migrated
end

-- ============================================================================
-- BACKGROUND CLEANUP TASK
-- Runs every hour to clean expired entries
-- ============================================================================

if box.info.ro == false then
    require('fiber').create(function()
        print('✓ Starting background cleanup task (runs every hour)')
        while true do
            require('fiber').sleep(3600)  -- 1 hour
            
            local ok, result = pcall(cleanup_expired)
            if ok then
                print(string.format(
                    'Cleanup: removed %d cache entries, %d reports',
                    result.cleaned_cache,
                    result.cleaned_reports
                ))
            else
                print('Cleanup error: ' .. tostring(result))
            end
        end
    end)
end

-- ============================================================================
-- INITIALIZATION COMPLETE
-- ============================================================================

print('========================================')
print('Tarantool initialization complete!')
print('Spaces: cache, reports, threads, persistent')
print('Background cleanup task: enabled')
print('========================================')

-- Print current stats
local stats = get_space_stats()
print(string.format('Current entries: cache=%d, reports=%d, threads=%d, persistent=%d',
    stats.cache, stats.reports, stats.threads, stats.persistent))
