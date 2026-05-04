import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { DatabaseSync } from 'node:sqlite'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const workspaceRoot = path.resolve(scriptDir, '..')
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), '.codex')
const recoveryRoot = path.join(workspaceRoot, 'recovery', 'codex_threads')
const sessionIndexPath = path.join(codexHome, 'session_index.jsonl')
const stateDbPath = path.join(codexHome, 'state_5.sqlite')

function ensureDir(dirPath) {
    fs.mkdirSync(dirPath, { recursive: true })
}

function readJson(filePath) {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'))
}

function readJsonLines(filePath) {
    if (!fs.existsSync(filePath)) {
        return []
    }

    return fs
        .readFileSync(filePath, 'utf8')
        .split(/\r?\n/)
        .filter(Boolean)
        .map((line) => JSON.parse(line))
}

function writeJsonLines(filePath, rows) {
    fs.writeFileSync(filePath, `${rows.map((row) => JSON.stringify(row)).join('\n')}\n`, 'utf8')
}

function isoToMs(isoString) {
    return new Date(isoString).getTime()
}

function isoToUnixSeconds(isoString) {
    const millis = Date.parse(isoString || '')
    return Number.isFinite(millis) ? Math.floor(millis / 1000) : Math.floor(Date.now() / 1000)
}

function isoAtOffset(baseIso, offsetMs) {
    return new Date(isoToMs(baseIso) + offsetMs).toISOString()
}

function stripDevicePrefix(value) {
    if (typeof value !== 'string') {
        return ''
    }

    return value.startsWith('\\\\?\\') ? value.slice(4) : value
}

function copyIfExists(sourcePath, targetPath) {
    if (fs.existsSync(sourcePath)) {
        fs.copyFileSync(sourcePath, targetPath)
    }
}

function pad2(value) {
    return `${value}`.padStart(2, '0')
}

function buildRolloutPath(threadId, isoString) {
    const baseDate = Number.isFinite(Date.parse(isoString || '')) ? new Date(isoString) : new Date()
    const year = `${baseDate.getFullYear()}`
    const month = pad2(baseDate.getMonth() + 1)
    const day = pad2(baseDate.getDate())
    const hour = pad2(baseDate.getHours())
    const minute = pad2(baseDate.getMinutes())
    const second = pad2(baseDate.getSeconds())
    const sessionDir = path.join(codexHome, 'sessions', year, month, day)
    const stamp = `${year}-${month}-${day}T${hour}-${minute}-${second}`
    return path.join(sessionDir, `rollout-${stamp}-${threadId}.jsonl`)
}

function normalizeThreadForCurrentHome(thread) {
    return {
        ...thread,
        cwd: stripDevicePrefix(thread.cwd) || workspaceRoot,
        rolloutPath: buildRolloutPath(thread.id, thread.createdAtIso || thread.updatedAtIso),
    }
}

function walkFiles(rootDir) {
    const results = []

    if (!fs.existsSync(rootDir)) {
        return results
    }

    for (const entry of fs.readdirSync(rootDir, { withFileTypes: true })) {
        const fullPath = path.join(rootDir, entry.name)
        if (entry.isDirectory()) {
            results.push(...walkFiles(fullPath))
            continue
        }

        results.push(fullPath)
    }

    return results
}

function findLatestSessionFile() {
    const sessionRoot = path.join(codexHome, 'sessions')
    const sessionFiles = walkFiles(sessionRoot).filter((filePath) => filePath.endsWith('.jsonl'))

    if (sessionFiles.length === 0) {
        throw new Error(`No session files found under ${sessionRoot}`)
    }

    sessionFiles.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)
    return sessionFiles[0]
}

function buildAssistantText(thread) {
    const sections = ['Recovered thread. Original Codex rollout file was missing, so this was reconstructed from local metadata and logs.']

    if (thread.assistantMessages.length > 0) {
        sections.push(
            ...thread.assistantMessages.map((message, index) => {
                const heading = `Recovered assistant message ${index + 1} (${message.phase})`
                return `${heading}\n\n${message.text}`
            }),
        )
    } else {
        sections.push('No assistant message text survived in the available logs. Only prompt metadata was recoverable.')
    }

    if (thread.toolCalls.length > 0) {
        sections.push(`Recovered tool calls:\n\n${thread.toolCalls.join('\n')}`)
    }

    return sections.join('\n\n---\n\n')
}

function buildSessionMeta(templateMeta, thread) {
    return {
        ...templateMeta,
        id: thread.id,
        timestamp: thread.createdAtIso ?? templateMeta.timestamp,
        cwd: stripDevicePrefix(thread.cwd) || stripDevicePrefix(templateMeta.cwd),
        source: thread.source || templateMeta.source,
        model_provider: thread.modelProvider || templateMeta.model_provider,
        cli_version: thread.cliVersion || templateMeta.cli_version,
    }
}

function buildDeveloperMessage(templateDeveloper) {
    if (templateDeveloper) {
        return templateDeveloper
    }

    return {
        type: 'response_item',
        payload: {
            type: 'message',
            role: 'developer',
            content: [
                {
                    type: 'input_text',
                    text: 'Recovered session file reconstructed from local Codex metadata.',
                },
            ],
        },
    }
}

function buildTurnEntries(template, thread) {
    const userText = thread.userMessages[0] || thread.firstUserMessage || thread.title
    const assistantText = buildAssistantText(thread)
    const startedAt = thread.createdAtIso || thread.updatedAtIso || new Date().toISOString()
    const finishedAt = thread.updatedAtIso || startedAt
    const turnId = `${thread.id}-recovered-turn`

    return [
        {
            timestamp: startedAt,
            type: 'event_msg',
            payload: {
                type: 'task_started',
                turn_id: turnId,
                model_context_window: 258400,
                collaboration_mode_kind: 'default',
            },
        },
        buildDeveloperMessage(template.developerMessage),
        {
            timestamp: isoAtOffset(startedAt, 10),
            type: 'response_item',
            payload: {
                type: 'message',
                role: 'user',
                content: [
                    {
                        type: 'input_text',
                        text: `${userText}\n`,
                    },
                ],
            },
        },
        {
            timestamp: isoAtOffset(startedAt, 11),
            type: 'event_msg',
            payload: {
                type: 'user_message',
                message: `${userText}\n`,
                images: [],
                local_images: [],
                text_elements: [],
            },
        },
        {
            timestamp: isoAtOffset(startedAt, 20),
            type: 'event_msg',
            payload: {
                type: 'agent_message',
                message: assistantText,
                phase: 'final_answer',
            },
        },
        {
            timestamp: isoAtOffset(startedAt, 21),
            type: 'response_item',
            payload: {
                type: 'message',
                role: 'assistant',
                phase: 'final_answer',
                content: [
                    {
                        type: 'output_text',
                        text: assistantText,
                    },
                ],
            },
        },
        {
            timestamp: finishedAt,
            type: 'event_msg',
            payload: {
                type: 'task_complete',
                turn_id: turnId,
                last_agent_message: assistantText,
            },
        },
    ]
}

function loadTemplate() {
    const currentSessionPath = findLatestSessionFile()
    const lines = readJsonLines(currentSessionPath)
    const sessionMetaLine = lines.find((line) => line.type === 'session_meta')
    const developerMessage = lines.find(
        (line) => line.type === 'response_item' && line.payload?.type === 'message' && line.payload?.role === 'developer',
    )
    const stateDb = new DatabaseSync(stateDbPath, { readonly: true })
    const templateThread = stateDb.prepare('SELECT * FROM threads ORDER BY updated_at DESC LIMIT 1').get()

    if (!sessionMetaLine?.payload) {
        throw new Error(`Could not locate session_meta template in ${currentSessionPath}`)
    }

    if (!templateThread) {
        throw new Error(`Could not locate a template thread in ${stateDbPath}`)
    }

    return {
        sessionMeta: sessionMetaLine.payload,
        developerMessage,
        threadRow: templateThread,
    }
}

function buildThreadRow(templateThread, thread) {
    const createdAt = isoToUnixSeconds(thread.createdAtIso || thread.updatedAtIso)
    const updatedAt = isoToUnixSeconds(thread.updatedAtIso || thread.createdAtIso)

    return {
        id: thread.id,
        rollout_path: thread.rolloutPath,
        created_at: createdAt,
        updated_at: updatedAt,
        source: thread.source || templateThread.source || 'vscode',
        model_provider: thread.modelProvider || templateThread.model_provider || 'openai',
        cwd: stripDevicePrefix(thread.cwd) || stripDevicePrefix(templateThread.cwd) || workspaceRoot,
        title: thread.title,
        sandbox_policy: thread.sandboxPolicy || templateThread.sandbox_policy,
        approval_mode: thread.approvalMode || templateThread.approval_mode || 'on-request',
        tokens_used: 0,
        has_user_event: thread.userMessages.length > 0 || Boolean(thread.firstUserMessage) ? 1 : 0,
        archived: thread.archived ? 1 : 0,
        archived_at: thread.archived ? updatedAt : null,
        git_sha: templateThread.git_sha ?? null,
        git_branch: templateThread.git_branch ?? null,
        git_origin_url: templateThread.git_origin_url ?? null,
        cli_version: thread.cliVersion || templateThread.cli_version || '',
        first_user_message: thread.firstUserMessage || thread.userMessages[0] || thread.title,
        agent_nickname: thread.agentNickname ?? null,
        agent_role: thread.agentRole ?? null,
        memory_mode: thread.memoryMode || templateThread.memory_mode || 'enabled',
    }
}

function upsertThreadRow(stateDb, templateThread, thread) {
    const row = buildThreadRow(templateThread, thread)
    const existing = stateDb.prepare('SELECT id FROM threads WHERE id = ?').get(thread.id)

    if (existing) {
        const updateRow = {
            id: row.id,
            rollout_path: row.rollout_path,
            updated_at: row.updated_at,
            cwd: row.cwd,
            title: row.title,
            sandbox_policy: row.sandbox_policy,
            approval_mode: row.approval_mode,
            cli_version: row.cli_version,
            first_user_message: row.first_user_message,
            archived: row.archived,
            archived_at: row.archived_at,
        }

        stateDb
            .prepare(
                `UPDATE threads
                 SET rollout_path = @rollout_path,
                     updated_at = @updated_at,
                     cwd = @cwd,
                     title = @title,
                     sandbox_policy = @sandbox_policy,
                     approval_mode = @approval_mode,
                     cli_version = @cli_version,
                     first_user_message = @first_user_message,
                     archived = @archived,
                     archived_at = @archived_at
                 WHERE id = @id`,
            )
            .run(updateRow)

        return 'updated'
    }

    stateDb
        .prepare(
            `INSERT INTO threads (
                id,
                rollout_path,
                created_at,
                updated_at,
                source,
                model_provider,
                cwd,
                title,
                sandbox_policy,
                approval_mode,
                tokens_used,
                has_user_event,
                archived,
                archived_at,
                git_sha,
                git_branch,
                git_origin_url,
                cli_version,
                first_user_message,
                agent_nickname,
                agent_role,
                memory_mode
            ) VALUES (
                @id,
                @rollout_path,
                @created_at,
                @updated_at,
                @source,
                @model_provider,
                @cwd,
                @title,
                @sandbox_policy,
                @approval_mode,
                @tokens_used,
                @has_user_event,
                @archived,
                @archived_at,
                @git_sha,
                @git_branch,
                @git_origin_url,
                @cli_version,
                @first_user_message,
                @agent_nickname,
                @agent_role,
                @memory_mode
            )`,
        )
        .run(row)

    return 'inserted'
}

function main() {
    if (!fs.existsSync(recoveryRoot)) {
        throw new Error(`Recovery folder not found: ${recoveryRoot}`)
    }

    const backupRoot = path.join(codexHome, 'recovery-backups', new Date().toISOString().replace(/[:.]/g, '-'))
    ensureDir(backupRoot)

    copyIfExists(sessionIndexPath, path.join(backupRoot, 'session_index.jsonl.bak'))
    copyIfExists(stateDbPath, path.join(backupRoot, 'state_5.sqlite.bak'))
    copyIfExists(`${stateDbPath}-shm`, path.join(backupRoot, 'state_5.sqlite-shm.bak'))
    copyIfExists(`${stateDbPath}-wal`, path.join(backupRoot, 'state_5.sqlite-wal.bak'))

    const template = loadTemplate()
    const recoveredThreadFiles = fs
        .readdirSync(recoveryRoot)
        .filter(
            (name) =>
                name.endsWith('.json') &&
                name !== 'summary.json' &&
                name !== 'live_rebuild_report.json',
        )
        .map((name) => path.join(recoveryRoot, name))

    const existingIndex = readJsonLines(sessionIndexPath)
    const indexById = new Map(existingIndex.map((row) => [row.id, row]))
    const stateDb = new DatabaseSync(stateDbPath)
    const touched = []
    const insertedThreadIds = []
    const updatedThreadIds = []

    for (const filePath of recoveredThreadFiles) {
        const thread = normalizeThreadForCurrentHome(readJson(filePath))
        const upsertAction = upsertThreadRow(stateDb, template.threadRow, thread)
        const rolloutPath = thread.rolloutPath
        const rolloutExists = fs.existsSync(rolloutPath)
        const rolloutSize = rolloutExists ? fs.statSync(rolloutPath).size : 0
        const needsSessionWrite = !(rolloutExists && rolloutSize > 0)

        if (needsSessionWrite) {
            ensureDir(path.dirname(rolloutPath))

            const sessionLines = [
                {
                    timestamp: thread.createdAtIso ?? new Date().toISOString(),
                    type: 'session_meta',
                    payload: buildSessionMeta(template.sessionMeta, thread),
                },
                ...buildTurnEntries(template, thread),
            ]

            if (rolloutExists) {
                copyIfExists(rolloutPath, path.join(backupRoot, `${path.basename(rolloutPath)}.bak`))
            }

            writeJsonLines(rolloutPath, sessionLines)
        }

        indexById.set(thread.id, {
            id: thread.id,
            thread_name: thread.title,
            updated_at: thread.updatedAtIso,
        })

        if (upsertAction === 'inserted') {
            insertedThreadIds.push(thread.id)
        } else {
            updatedThreadIds.push(thread.id)
        }

        if (needsSessionWrite) {
            touched.push({
                id: thread.id,
                rolloutPath,
                title: thread.title,
            })
        }
    }

    const mergedIndex = [...indexById.values()].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
    writeJsonLines(sessionIndexPath, mergedIndex)

    const report = {
        codexHome,
        backupRoot,
        touched,
        insertedThreadIds,
        updatedThreadIds,
        mergedIndexCount: mergedIndex.length,
    }

    fs.writeFileSync(path.join(workspaceRoot, 'recovery', 'codex_threads', 'live_rebuild_report.json'), `${JSON.stringify(report, null, 2)}\n`)
    console.log(JSON.stringify(report, null, 2))
}

main()
