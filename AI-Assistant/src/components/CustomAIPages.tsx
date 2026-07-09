import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
    Page,
    Layout,
    Card,
    Text,
    BlockStack,
    Button,
    Badge,
    Toast,
    TextField,
    Modal,
    Icon,
    InlineStack,
    Box,
} from '@shopify/polaris';
import {
    EditIcon,
    DeleteIcon,
    SearchIcon,
    PlusIcon,
    PageIcon,
} from '@shopify/polaris-icons';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import { Table } from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row';
import TableCell from '@tiptap/extension-table-cell';
import TableHeader from '@tiptap/extension-table-header';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import CodeBlock from '@tiptap/extension-code-block';
import Blockquote from '@tiptap/extension-blockquote';

// Types
interface CustomData {
    id: number;
    title: string;
    value: string;
    is_enabled: number;
    created_at?: string;
    updated_at?: string;
}
const getCurrentShop = (): string => {
    // 1. Extract shop from URL path pattern: /store/{shop-name}/
    const pathMatch = window.location.pathname.match(/\/store\/([^\/]+)/);
    if (pathMatch && pathMatch[1]) {
        const shop = pathMatch[1];
        localStorage.setItem('current_shop', shop);
        return shop;
    }

    // 2. Check URL query parameters (for iframe embeds)
    const urlParams = new URLSearchParams(window.location.search);
    const shopParam = urlParams.get('shop');
    if (shopParam) {
        localStorage.setItem('current_shop', shopParam);
        return shopParam;
    }

    // 3. Check localStorage for previously selected shop
    const storedShop = localStorage.getItem('current_shop');
    if (storedShop) {
        return storedShop;
    }

    // 4. Check Shopify App Bridge
    if ((window as any).Shopify && (window as any).Shopify.shop) {
        const shopifyShop = (window as any).Shopify.shop;
        localStorage.setItem('current_shop', shopifyShop);
        return shopifyShop;
    }

    // 5. Default fallback
    return null;
};

const SHOP = getCurrentShop();
console.log("Shop : ", SHOP);
// Also add .myshopify.com if needed for API calls
const getShopDomain = (): string => {
    const shop = getCurrentShop();
    if (shop && !shop.includes('.myshopify.com')) {
        return `${shop}.myshopify.com`;
    }
    return shop;
};
const API_BASE_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:5054';

const fetchWithTimeout = async (url: string, options?: RequestInit, timeout = 30000) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
        const response = await fetch(url, {
            signal: controller.signal,
            ...options,  // ✅ This spreads method, headers, body
        });
        clearTimeout(timeoutId);
        return response;
    } catch (error: any) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error(`Request timeout after ${timeout / 1000}s`);
        }
        throw error;
    }
};

// Validation Functions
const containsEmojiOrIcon = (text: string): boolean => {
    // Emoji ranges
    const emojiRegex = /[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F900}-\u{1F9FF}\u{1F1E6}-\u{1F1FF}]/u;

    // Icon characters
    const iconRegex = /[✓✗★☆♥♦♣♠♂♀♪♫☀☁☂☃☄★☆☎☏✉✍✎✏✐✑✒✓✔✕✖✗✘✙✚✛✜✝✞✟✠✡✢✣✤✥✦✧✩✪✫✬✭✮✯✰✱✲✳✴✵✶✷✸✹✺✻✼✽✾✿❀❁❂❃❄❅❆❇❈❉❊❋]/;

    // Font icon patterns
    const fontIconRegex = /class=["'][^"']*(?:fa-|material-icons|icon-|glyphicon|svg-inline)[^"']*["']/i;

    return emojiRegex.test(text) || iconRegex.test(text) || fontIconRegex.test(text);
};

const validateTitle = (title: string): { isValid: boolean; message?: string } => {
    if (!title.trim()) {
        return { isValid: false, message: "Title is required." };
    }

    if (containsEmojiOrIcon(title)) {
        return { isValid: false, message: "Emojis and icons are not allowed in titles. Please use text only." };
    }

    // Allow only letters, numbers, spaces, and basic punctuation
    const validCharsRegex = /^[a-zA-Z0-9\s\-_,.:;()&]+$/;
    if (!validCharsRegex.test(title)) {
        return { isValid: false, message: "Title contains invalid characters. Use letters, numbers, and basic punctuation only." };
    }

    if (title.length > 200) {
        return { isValid: false, message: "Title is too long. Maximum 200 characters allowed." };
    }

    return { isValid: true };
};

const validateContent = (html: string): { isValid: boolean; message?: string } => {
    // Strip HTML tags to get plain text
    const plainText = html.replace(/<[^>]*>/g, '').trim();

    if (!plainText) {
        return { isValid: false, message: "Content cannot be empty." };
    }

    if (containsEmojiOrIcon(plainText)) {
        return { isValid: false, message: "Emojis and icons are not allowed in content. Please use text only." };
    }

    // Check for icon images
    const iconImageRegex = /<img[^>]+(icon|logo|emoji|symbol)[^>]*>/i;
    if (iconImageRegex.test(html)) {
        return { isValid: false, message: "Icon images are not allowed. Please use text only." };
    }

    return { isValid: true };
};

// Toggle Switch Component
const ToggleSwitch = ({ enabled, onChange, disabled = false }: { enabled: boolean; onChange: (checked: boolean) => void; disabled?: boolean }) => {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={enabled}
            disabled={disabled}
            onClick={() => onChange(!enabled)}
            style={{
                position: 'relative',
                display: 'inline-block',
                width: '44px',
                height: '24px',
                background: enabled ? '#008060' : '#c9cccf',
                borderRadius: '12px',
                transition: 'all 0.2s ease',
                cursor: disabled ? 'not-allowed' : 'pointer',
                border: 'none',
                opacity: disabled ? 0.6 : 1,
                outline: 'none',
            }}
        >
            <span
                style={{
                    position: 'absolute',
                    top: '2px',
                    left: enabled ? '22px' : '2px',
                    width: '20px',
                    height: '20px',
                    background: 'white',
                    borderRadius: '50%',
                    transition: 'all 0.2s ease',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                }}
            />
        </button>
    );
};

// Confirmation Modal Component
const ConfirmationModal = ({ open, title, message, onConfirm, onClose, loading }: any) => {
    return (
        <Modal
            open={open}
            onClose={onClose}
            title={title}
            size="small"
            primaryAction={{
                content: 'Delete',
                onAction: onConfirm,
                destructive: true,
                loading: loading,
            }}
            secondaryActions={[
                {
                    content: 'Cancel',
                    onAction: onClose,
                },
            ]}
        >
            <Modal.Section>
                <Text as="p" variant="bodyMd">{message}</Text>
            </Modal.Section>
        </Modal>
    );
};

// Rich Text Editor Toolbar Button
const ToolbarButton = ({ onClick, isActive, disabled, children, title }: any) => (
    <button
        onClick={onClick}
        disabled={disabled}
        title={title}
        style={{
            padding: '6px 10px',
            margin: '0 2px',
            border: '1px solid #e1e3e5',
            background: isActive ? '#e6f7f0' : '#ffffff',
            borderRadius: '4px',
            cursor: disabled ? 'not-allowed' : 'pointer',
            fontSize: '13px',
            fontWeight: isActive ? '600' : '400',
            color: disabled ? '#c9cccf' : '#202223',
            transition: 'all 0.2s',
        }}
    >
        {children}
    </button>
);

// Rich Text Editor Component with Validation
const RichTextEditor = ({ content, onChange, onValidationError }: { content: string; onChange: (html: string) => void; onValidationError?: (message: string) => void }) => {
    const editor = useEditor({
        extensions: [
            StarterKit.configure({
                heading: { levels: [1, 2, 3, 4] }, // Limit to H1-H4 only
            }),
            Underline,
            TextAlign.configure({ types: ['heading', 'paragraph'] }),
            Link.configure({ openOnClick: false }),
            Table.configure({ resizable: true }),
            TableRow,
            TableCell,
            TableHeader,
            TaskList,
            TaskItem.configure({ nested: true }),
            CodeBlock,
            Blockquote,
            Placeholder.configure({ placeholder: 'Start writing your content here...' }),
        ],
        content: content || '',
        onUpdate: ({ editor }) => {
            const newContent = editor.getHTML();
            const validation = validateContent(newContent);
            if (validation.isValid) {
                onChange(newContent);
            } else {
                // Revert to previous content
                editor.commands.setContent(content || '');
                if (onValidationError) {
                    onValidationError(validation.message || "Invalid content detected");
                }
            }
        },
        editorProps: { attributes: { class: 'rich-text-editor' } },
    });

    useEffect(() => {
        if (editor && content !== editor.getHTML()) {
            editor.commands.setContent(content || '');
        }
    }, [content, editor]);

    // Handle paste events to prevent emojis/icons
    useEffect(() => {
        if (editor) {
            const editorElement = editor.view.dom;
            const handlePaste = (e: ClipboardEvent) => {
                const pastedText = e.clipboardData?.getData('text/plain') || '';
                if (containsEmojiOrIcon(pastedText)) {
                    e.preventDefault();
                    if (onValidationError) {
                        onValidationError("Emojis and icons cannot be pasted. Please use plain text only.");
                    }
                }
            };
            editorElement.addEventListener('paste', handlePaste);
            return () => editorElement.removeEventListener('paste', handlePaste);
        }
    }, [editor, onValidationError]);

    useEffect(() => {
        const style = document.createElement('style');
        style.textContent = `
            .rich-text-editor {
                min-height: 400px;
                padding: 16px;
                border: 1px solid #e1e3e5;
                border-radius: 4px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
                line-height: 1.6;
                font-size: 14px;
                background: #fff;
            }
            .rich-text-editor:focus {
                outline: none;
                border-color: #008060;
                box-shadow: 0 0 0 1px #008060;
            }
            .rich-text-editor p { margin: 0 0 1em 0; }
            .rich-text-editor h1 { font-size: 2em; margin: 0.67em 0; font-weight: 700; }
            .rich-text-editor h2 { font-size: 1.5em; margin: 0.75em 0; font-weight: 600; }
            .rich-text-editor h3 { font-size: 1.17em; margin: 0.83em 0; font-weight: 600; }
            .rich-text-editor h4 { font-size: 1em; margin: 1.12em 0; font-weight: 600; }
            .rich-text-editor ul, .rich-text-editor ol { margin: 1em 0; padding-left: 2em; }
            .rich-text-editor li { margin: 0.25em 0; }
            .rich-text-editor hr { margin: 1em 0; border: none; border-top: 2px solid #e1e3e5; }
            .rich-text-editor blockquote {
                margin: 1em 0;
                padding-left: 1em;
                border-left: 3px solid #008060;
                color: #6d7175;
                font-style: italic;
            }
            .rich-text-editor code {
                background: #f6f6f7;
                padding: 2px 4px;
                border-radius: 3px;
                font-family: 'Monaco', 'Menlo', monospace;
                font-size: 0.9em;
            }
            .rich-text-editor pre {
                background: #1e1e1e;
                color: #d4d4d4;
                padding: 12px;
                border-radius: 6px;
                overflow-x: auto;
                font-family: 'Monaco', 'Menlo', monospace;
                font-size: 13px;
                margin: 1em 0;
            }
            .rich-text-editor pre code {
                background: none;
                padding: 0;
                color: inherit;
            }
            .rich-text-editor a {
                color: #008060;
                text-decoration: underline;
                cursor: pointer;
            }
            .rich-text-editor table {
                width: 100%;
                border-collapse: collapse;
                margin: 1em 0;
            }
            .rich-text-editor th,
            .rich-text-editor td {
                border: 1px solid #e1e3e5;
                padding: 8px 12px;
                text-align: left;
            }
            .rich-text-editor th {
                background: #f6f6f7;
                font-weight: 600;
            }
            .rich-text-editor .ProseMirror-selectednode {
                outline: 2px solid #008060;
            }
            .rich-text-editor .ProseMirror-placeholder {
                color: #b0b7bf;
                pointer-events: none;
                height: 0;
            }
        `;
        document.head.appendChild(style);
        return () => document.head.removeChild(style);
    }, []);

    if (!editor) return null;

    const addLink = () => {
        const url = window.prompt('Enter URL:');
        if (url) editor.chain().focus().setLink({ href: url }).run();
    };

    const addTable = () => {
        const rows = parseInt(window.prompt('Number of rows:', '3') || '3');
        const cols = parseInt(window.prompt('Number of columns:', '3') || '3');
        if (rows && cols) editor.chain().focus().insertTable({ rows, cols, withHeaderRow: true }).run();
    };

    return (
        <div>
            <div style={{
                border: '1px solid #e1e3e5',
                borderBottom: 'none',
                borderRadius: '4px 4px 0 0',
                padding: '8px',
                background: '#f9fafb',
                display: 'flex',
                flexWrap: 'wrap',
                gap: '4px',
                position: 'sticky',
                top: 0,
                zIndex: 10,
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '2px', paddingRight: '8px', borderRight: '1px solid #e1e3e5' }}>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleBold().run()} isActive={editor.isActive('bold')} title="Bold"><strong>B</strong></ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleItalic().run()} isActive={editor.isActive('italic')} title="Italic"><em>I</em></ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleUnderline().run()} isActive={editor.isActive('underline')} title="Underline"><u>U</u></ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleStrike().run()} isActive={editor.isActive('strike')} title="Strikethrough"><s>S</s></ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleCode().run()} isActive={editor.isActive('code')} title="Code">&lt;/&gt;</ToolbarButton>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '2px', paddingRight: '8px', borderRight: '1px solid #e1e3e5' }}>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} isActive={editor.isActive('heading', { level: 1 })} title="Heading 1">H1</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} isActive={editor.isActive('heading', { level: 2 })} title="Heading 2">H2</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} isActive={editor.isActive('heading', { level: 3 })} title="Heading 3">H3</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 4 }).run()} isActive={editor.isActive('heading', { level: 4 })} title="Heading 4">H4</ToolbarButton>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '2px', paddingRight: '8px', borderRight: '1px solid #e1e3e5' }}>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleBulletList().run()} isActive={editor.isActive('bulletList')} title="Bullet List">• List</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleOrderedList().run()} isActive={editor.isActive('orderedList')} title="Numbered List">1. List</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleTaskList().run()} isActive={editor.isActive('taskList')} title="Task List">☐ Task</ToolbarButton>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '2px', paddingRight: '8px', borderRight: '1px solid #e1e3e5' }}>
                    <ToolbarButton onClick={() => editor.chain().focus().setTextAlign('left').run()} isActive={editor.isActive({ textAlign: 'left' })} title="Align Left">◀</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().setTextAlign('center').run()} isActive={editor.isActive({ textAlign: 'center' })} title="Center">═</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().setTextAlign('right').run()} isActive={editor.isActive({ textAlign: 'right' })} title="Align Right">▶</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().setTextAlign('justify').run()} isActive={editor.isActive({ textAlign: 'justify' })} title="Justify">☰</ToolbarButton>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '2px', paddingRight: '8px', borderRight: '1px solid #e1e3e5' }}>
                    <ToolbarButton onClick={addLink} title="Insert Link">🔗</ToolbarButton>
                    <ToolbarButton onClick={addTable} title="Insert Table">▦</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().setHorizontalRule().run()} title="Divider">—</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleBlockquote().run()} isActive={editor.isActive('blockquote')} title="Quote">"</ToolbarButton>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '2px', paddingRight: '8px', borderRight: '1px solid #e1e3e5' }}>
                    <ToolbarButton onClick={() => editor.chain().focus().toggleCodeBlock().run()} isActive={editor.isActive('codeBlock')} title="Code Block">{`{ }`}</ToolbarButton>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                    <ToolbarButton onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} title="Undo">↶</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} title="Redo">↷</ToolbarButton>
                    <ToolbarButton onClick={() => editor.chain().focus().clearNodes().run()} title="Clear Formatting">✖</ToolbarButton>
                </div>
            </div>
            <EditorContent editor={editor} />
        </div>
    );
};

// Data Editor Modal
const DataEditorModal: React.FC<{
    open: boolean;
    item: CustomData | null;
    onClose: () => void;
    onSave: (title: string, value: string) => void;
    onToast: (message: string) => void;
}> = ({ open, item, onClose, onSave, onToast }) => {
    const [title, setTitle] = useState('');
    const [value, setValue] = useState('');
    const [titleError, setTitleError] = useState(false);

    useEffect(() => {
        if (open) {
            setTitle(item?.title ?? '');
            setValue(item?.value ?? '');
            setTitleError(false);
        }
    }, [item, open]);

    const handleSave = () => {
        // Validate title
        const titleValidation = validateTitle(title);
        if (!titleValidation.isValid) {
            setTitleError(true);
            onToast(titleValidation.message || "Invalid title");
            return;
        }

        // Validate content
        const contentValidation = validateContent(value);
        if (!contentValidation.isValid) {
            onToast(contentValidation.message || "Invalid content");
            return;
        }

        onSave(title, value);
        onClose();
    };

    const handleValidationError = (message: string) => {
        onToast(message);
    };

    return (
        <Modal
            open={open}
            onClose={onClose}
            title={item ? 'Edit Data Entry' : 'Create New Data Entry'}
            size="large"
            primaryAction={{ content: item ? 'Save Changes' : 'Create Entry', onAction: handleSave }}
            secondaryActions={[{ content: 'Cancel', onAction: onClose }]}
        >
            <Modal.Section>
                <BlockStack gap="500">
                    <div>
                        <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#3a3d40', marginBottom: '6px' }}>
                            Title / Key <span style={{ color: '#d82c0d' }}>*</span>
                        </label>
                        <input
                            type="text"
                            style={{
                                width: '100%',
                                height: '38px',
                                padding: '0 12px',
                                fontSize: '14px',
                                border: `1px solid ${titleError ? '#d82c0d' : '#c9cccf'}`,
                                borderRadius: '6px',
                                fontFamily: 'inherit',
                                color: '#202223',
                                outline: 'none',
                                boxSizing: 'border-box',
                            }}
                            placeholder="Enter title (letters, numbers, spaces, and basic punctuation only)..."
                            value={title}
                            onChange={e => { setTitle(e.target.value); setTitleError(false); }}
                        />
                        {titleError && (
                            <span style={{ display: 'block', marginTop: 5, fontSize: 12, color: '#d82c0d' }}>
                                Please enter a valid title. No emojis, icons, or special characters allowed.
                            </span>
                        )}
                    </div>
                    <div>
                        <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#3a3d40', marginBottom: '6px' }}>
                            Value / Content
                        </label>
                        <RichTextEditor
                            content={value}
                            onChange={setValue}
                            onValidationError={handleValidationError}
                        />
                    </div>
                </BlockStack>
            </Modal.Section>
        </Modal>
    );
};

// Main Component
export default function CustomDataManager() {
    const [items, setItems] = useState<CustomData[]>([]);
    const [searchValue, setSearchValue] = useState('');
    const [filterEnabled, setFilterEnabled] = useState<'all' | 'enabled' | 'disabled'>('all');
    const [toastMsg, setToastMsg] = useState('');
    const [showToast, setShowToast] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);
    const [editingItem, setEditingItem] = useState<CustomData | null>(null);
    const [loading, setLoading] = useState(true);
    const [bulkActionLoading, setBulkActionLoading] = useState(false);
    const [selectedItems, setSelectedItems] = useState<Set<number>>(new Set());
    const [togglingItemId, setTogglingItemId] = useState<number | null>(null);
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
    const [itemToDelete, setItemToDelete] = useState<number | null>(null);
    const [deleting, setDeleting] = useState(false);

    const toast = useCallback((msg: string) => { setToastMsg(msg); setShowToast(true); setTimeout(() => setShowToast(false), 3000); }, []);

    const fetchItems = useCallback(async () => {
        try {
            let url = `${API_BASE_URL}/api/custom-data?shop=${SHOP}&limit=500`;
            if (filterEnabled !== 'all') {
                url += `&enabled_filter=${filterEnabled}`;
            }
            const response = await fetchWithTimeout(url);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            setItems(data.data || []);
        } catch (err) {
            console.error('Error fetching data:', err);
            toast('Failed to load data');
        } finally {
            setLoading(false);
        }
    }, [toast, filterEnabled]);

    if (!SHOP) {
        return (
            <>
                <Page title="Custom Data Manager">
                    <div style={{ padding: '60px', textAlign: 'center' }}>
                        <Text as="p" variant="headingLg" tone="critical">
                            ⚠️ Unable to detect Store
                        </Text>
                        <Text as="p" variant="bodyMd" tone="subdued" style={{ marginTop: '16px' }}>
                            Please access this page from within your Shopify store's admin panel.
                        </Text>
                        <Text as="p" variant="bodySm" tone="subdued" style={{ marginTop: '8px' }}>
                            Make sure you are logged into your Shopify admin and accessing the app from the correct URL.
                        </Text>
                    </div>
                </Page>
            </>
        );
    }

    const createItem = async (title: string, value: string) => {
        const response = await fetchWithTimeout(`${API_BASE_URL}/api/custom-data`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, value, shop: SHOP, is_enabled: 1 }),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create');
        }
        return response.json();
    };

    const updateItem = async (id: number, title: string, value: string) => {
        const response = await fetchWithTimeout(`${API_BASE_URL}/api/custom-data/${id}?shop=${SHOP}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, value }),
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update');
        }
        return response.json();
    };

    const deleteItem = async (id: number) => {
        const response = await fetchWithTimeout(`${API_BASE_URL}/api/custom-data/${id}?shop=${SHOP}`, {
            method: 'DELETE',
        });
        if (!response.ok) throw new Error('Failed to delete');
        return true;
    };

    const toggleItemEnabled = async (itemId: number, currentStatus: number) => {
        setTogglingItemId(itemId);
        const newStatus = currentStatus === 1 ? 0 : 1;

        // Optimistic update
        setItems(prev => prev.map(item =>
            item.id === itemId ? { ...item, is_enabled: newStatus } : item
        ));

        try {
            const response = await fetchWithTimeout(`${API_BASE_URL}/api/custom-data/${itemId}/toggle-enabled?shop=${SHOP}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ is_enabled: newStatus }),  // ✅ Add this
            });

            if (!response.ok) {
                throw new Error('Failed to update status');
            }

            const result = await response.json();
            toast(`Entry ${result.is_enabled === 1 ? 'enabled' : 'disabled'} in AI successfully`);

        } catch (err) {
            console.error('Toggle error:', err);
            toast('Failed to update status');
            // Revert optimistic update
            setItems(prev => prev.map(item =>
                item.id === itemId ? { ...item, is_enabled: currentStatus } : item
            ));
        } finally {
            setTogglingItemId(null);
        }
    };

    const bulkToggleEnabled = async (enable: boolean) => {
        if (selectedItems.size === 0) {
            toast('Please select at least one entry');
            return;
        }

        setBulkActionLoading(true);
        const itemIds = Array.from(selectedItems);
        const isEnabledValue = enable ? 1 : 0;

        // Optimistic update
        setItems(prev => prev.map(item =>
            selectedItems.has(item.id) ? { ...item, is_enabled: isEnabledValue } : item
        ));

        try {
            const response = await fetchWithTimeout(`${API_BASE_URL}/api/custom-data/bulk-toggle-enabled?shop=${SHOP}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    data_ids: itemIds,
                    is_enabled: isEnabledValue
                }),
            });

            if (!response.ok) {
                throw new Error('Bulk update failed');
            }

            toast(`${itemIds.length} entries ${enable ? 'enabled' : 'disabled'} in AI successfully`);
            setSelectedItems(new Set());

        } catch (err) {
            console.error('Bulk update error:', err);
            toast('Failed to update entries');
            // Revert optimistic update by refetching
            await fetchItems();
        } finally {
            setBulkActionLoading(false);
        }
    };

    const handleSelectItem = (itemId: number, checked: boolean) => {
        const newSelected = new Set(selectedItems);
        if (checked) newSelected.add(itemId);
        else newSelected.delete(itemId);
        setSelectedItems(newSelected);
    };

    const handleSelectAll = (checked: boolean) => {
        if (checked) {
            const allIds = new Set(filtered.map(item => item.id));
            setSelectedItems(allIds);
        } else {
            setSelectedItems(new Set());
        }
    };

    useEffect(() => {
        fetchItems();
    }, [fetchItems]);

    const handleSave = async (title: string, value: string) => {
        try {
            if (editingItem) {
                await updateItem(editingItem.id, title, value);
                setItems(prev => prev.map(i => i.id === editingItem.id ? { ...i, title, value, updated_at: new Date().toISOString() } : i));
                toast('Entry updated successfully.');
            } else {
                const newItem = await createItem(title, value);
                setItems(prev => [{ ...newItem, id: newItem.id, title, value, is_enabled: 1 }, ...prev]);
                toast('Entry created successfully.');
            }
        } catch (err: any) {
            toast(err.message || 'Failed to save. Please try again.');
        }
    };

    const handleDeleteClick = (id: number) => {
        setItemToDelete(id);
        setDeleteModalOpen(true);
    };

    const handleConfirmDelete = async () => {
        if (!itemToDelete) return;
        setDeleting(true);
        try {
            await deleteItem(itemToDelete);
            setItems(prev => prev.filter(i => i.id !== itemToDelete));
            setSelectedItems(prev => {
                const newSet = new Set(prev);
                newSet.delete(itemToDelete);
                return newSet;
            });
            toast('Entry deleted successfully.');
        } catch (err) {
            toast('Failed to delete.');
        } finally {
            setDeleting(false);
            setDeleteModalOpen(false);
            setItemToDelete(null);
        }
    };

    const openCreate = () => { setEditingItem(null); setModalOpen(true); };
    const openEdit = (item: CustomData) => { setEditingItem(item); setModalOpen(true); };

    const filtered = items.filter(item => {
        if (filterEnabled !== 'all') {
            const isEnabled = filterEnabled === 'enabled' ? 1 : 0;
            if (item.is_enabled !== isEnabled) return false;
        }
        if (searchValue) {
            const q = searchValue.toLowerCase();
            return item.title.toLowerCase().includes(q) || item.value.toLowerCase().includes(q);
        }
        return true;
    });

    const stats = {
        total: items.length,
        enabled: items.filter(i => i.is_enabled === 1).length,
        disabled: items.filter(i => i.is_enabled === 0).length,
    };

    if (loading) {
        return (
            <Page title="Custom Data Manager">
                <div style={{ display: 'flex', justifyContent: 'center', padding: '60px' }}>Loading...</div>
            </Page>
        );
    }

    return (
        <Page
            title="Custom Data Manager"
            subtitle="Store and manage key-value pairs with rich text support (No emojis or icons allowed)"
            primaryAction={{
                content: 'Create New Entry',
                onAction: openCreate,
                icon: <Icon source={PlusIcon} tone="base" />,
            }}
        >
            <Layout>
                <Layout.Section>
                    <BlockStack gap="500">
                        {selectedItems.size > 0 && (
                            <Card>
                                <InlineStack align="space-between" blockAlign="center">
                                    <Text as="p" variant="bodyMd">
                                        <strong>{selectedItems.size}</strong> entr{selectedItems.size !== 1 ? 'ies' : 'y'} selected
                                    </Text>
                                    <InlineStack gap="200">
                                        <Button onClick={() => bulkToggleEnabled(true)} loading={bulkActionLoading} disabled={bulkActionLoading} size="slim">Enable Selected</Button>
                                        <Button onClick={() => bulkToggleEnabled(false)} loading={bulkActionLoading} disabled={bulkActionLoading} tone="critical" size="slim">Disable Selected</Button>
                                        <Button onClick={() => setSelectedItems(new Set())} size="slim">Clear Selection</Button>
                                    </InlineStack>
                                </InlineStack>
                            </Card>
                        )}

                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                            <Card>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '4px 0' }}>
                                    <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #008060 0%, #00a880 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <Icon source={PageIcon} tone="base" color="white" />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', fontWeight: 500, color: '#6d7175' }}>Total Entries</div>
                                        <div style={{ fontSize: '28px', fontWeight: 700, color: '#202223' }}>{stats.total}</div>
                                    </div>
                                </div>
                            </Card>
                            <Card>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '4px 0' }}>
                                    <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #5c6ac4 0%, #7b8ad4 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <Icon source={PageIcon} tone="base" color="white" />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', fontWeight: 500, color: '#6d7175' }}>Enabled</div>
                                        <div style={{ fontSize: '28px', fontWeight: 700, color: '#202223' }}>{stats.enabled}</div>
                                    </div>
                                </div>
                            </Card>
                            <Card>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '4px 0' }}>
                                    <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #e86339 0%, #ff8a5c 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <Icon source={PageIcon} tone="base" color="white" />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '12px', fontWeight: 500, color: '#6d7175' }}>Disabled</div>
                                        <div style={{ fontSize: '28px', fontWeight: 700, color: '#202223' }}>{stats.disabled}</div>
                                    </div>
                                </div>
                            </Card>
                        </div>

                        <Card padding="0">
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px', padding: '16px 20px 14px', borderBottom: '1px solid #f1f2f3' }}>
                                <BlockStack gap="050">
                                    <Text as="h2" variant="headingMd">Data Entries</Text>
                                    <Text as="p" variant="bodySm" tone="subdued">{filtered.length} of {stats.total} entries</Text>
                                </BlockStack>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                                    <select style={{ height: '34px', padding: '0 10px', borderRadius: '6px', border: '1px solid #c9cccf', background: '#fff', fontSize: '13px', cursor: 'pointer' }} value={filterEnabled} onChange={e => setFilterEnabled(e.target.value as any)}>
                                        <option value="all">All ({stats.total})</option>
                                        <option value="enabled">Enabled ({stats.enabled})</option>
                                        <option value="disabled">Disabled ({stats.disabled})</option>
                                    </select>
                                    <div style={{ width: '230px' }}>
                                        <TextField label="Search" labelHidden value={searchValue} onChange={setSearchValue} placeholder="Search by title or value..." autoComplete="off" clearButton onClearButtonClick={() => setSearchValue('')} prefix={<Icon source={SearchIcon} tone="base" />} />
                                    </div>
                                </div>
                            </div>

                            {filtered.length > 0 ? (
                                <div style={{ overflowX: 'auto' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13.5px' }}>
                                        <thead>
                                            <tr style={{ borderBottom: '2px solid #e5e7ea', background: '#f8f9fa' }}>
                                                <th style={{ padding: '11px 16px', textAlign: 'left', fontSize: '11.5px', fontWeight: 600, color: '#6d7175', textTransform: 'uppercase', width: '5%' }}>
                                                    <input type="checkbox" checked={selectedItems.size === filtered.length && filtered.length > 0} onChange={(e) => handleSelectAll(e.target.checked)} style={{ cursor: 'pointer' }} />
                                                </th>
                                                <th style={{ padding: '11px 16px', textAlign: 'left', fontSize: '11.5px', fontWeight: 600, color: '#6d7175', textTransform: 'uppercase', width: '20%' }}>Title / Key</th>
                                                <th style={{ padding: '11px 16px', textAlign: 'left', fontSize: '11.5px', fontWeight: 600, color: '#6d7175', textTransform: 'uppercase', width: '35%' }}>Value</th>
                                                <th style={{ padding: '11px 16px', textAlign: 'left', fontSize: '11.5px', fontWeight: 600, color: '#6d7175', textTransform: 'uppercase', width: '15%' }}>Status</th>
                                                <th style={{ padding: '11px 16px', textAlign: 'right', fontSize: '11.5px', fontWeight: 600, color: '#6d7175', textTransform: 'uppercase', width: '25%' }}>Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {filtered.map(item => {
                                                const plainText = item.value.replace(/<[^>]*>/g, '');
                                                return (
                                                    <tr key={item.id} style={{ borderBottom: '1px solid #f1f2f3' }}>
                                                        <td style={{ padding: '14px 16px', verticalAlign: 'middle' }}>
                                                            <input type="checkbox" checked={selectedItems.has(item.id)} onChange={(e) => handleSelectItem(item.id, e.target.checked)} style={{ cursor: 'pointer' }} />
                                                        </td>
                                                        <td style={{ padding: '14px 16px', verticalAlign: 'middle' }}>
                                                            <Text as="p" variant="bodyMd" fontWeight="medium">{item.title}</Text>
                                                            <Text as="p" variant="bodySm" tone="subdued">ID: {item.id}</Text>
                                                        </td>
                                                        <td style={{ padding: '14px 16px', verticalAlign: 'middle' }}>
                                                            <Text as="p" variant="bodySm" tone="subdued">{plainText.length > 80 ? plainText.substring(0, 80) + '...' : plainText || '—'}</Text>
                                                        </td>
                                                        <td style={{ padding: '14px 16px', verticalAlign: 'middle' }}>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                                <ToggleSwitch enabled={item.is_enabled === 1} onChange={() => toggleItemEnabled(item.id, item.is_enabled)} disabled={bulkActionLoading || togglingItemId === item.id} />
                                                                <span style={{ fontSize: '12px', color: item.is_enabled === 1 ? '#008060' : '#8a8f96' }}>{item.is_enabled === 1 ? 'ON' : 'OFF'}</span>
                                                            </div>
                                                        </td>
                                                        <td style={{ padding: '14px 16px', verticalAlign: 'middle', textAlign: 'right' }}>
                                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '6px' }}>
                                                                <Button size="slim" icon={<Icon source={EditIcon} tone="base" />} onClick={() => openEdit(item)}>Edit</Button>
                                                                <Button size="slim" icon={<Icon source={DeleteIcon} tone="base" />} onClick={() => handleDeleteClick(item.id)} tone="critical" />
                                                            </div>
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '10px', padding: '52px 24px', color: '#8a8f96' }}>
                                    <Icon source={PageIcon} tone="subdued" />
                                    <Text as="p" variant="bodyMd" tone="subdued">{searchValue ? 'No entries match your search.' : 'No entries yet — create your first one!'}</Text>
                                    {!searchValue && <Button onClick={openCreate} variant="primary" size="slim">Create New Entry</Button>}
                                </div>
                            )}
                        </Card>
                    </BlockStack>
                </Layout.Section>
            </Layout>

            <DataEditorModal
                open={modalOpen}
                item={editingItem}
                onClose={() => setModalOpen(false)}
                onSave={handleSave}
                onToast={toast}
            />

            <ConfirmationModal
                open={deleteModalOpen}
                title="Delete Entry"
                message="Are you sure you want to delete this entry? This action cannot be undone."
                onConfirm={handleConfirmDelete}
                onClose={() => setDeleteModalOpen(false)}
                loading={deleting}
            />

            {showToast && <Toast content={toastMsg} onDismiss={() => setShowToast(false)} />}
        </Page>
    );
}