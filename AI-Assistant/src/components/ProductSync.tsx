// ProductSync.tsx - Simplified with inline Add Info for each product
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Page,
  Layout,
  Card,
  Text,
  BlockStack,
  Button,
  InlineStack,
  Badge,
  DataTable,
  TextField,
  Banner,
  Spinner,
  Box,
  Checkbox,
  Modal,
  Tabs,
  Divider,
} from '@shopify/polaris';
import { Icon } from '@shopify/polaris';
import {
  RefreshIcon,
  SearchIcon,
  CalendarIcon,
  ContentIcon,
  ClockIcon,
  PackageIcon,
  CollectionListIcon,
  ImageIcon,
  DataTableIcon,
  DatabaseIcon,
  NoteIcon,
  EditIcon,
  DeleteIcon,
  PlusIcon,
} from '@shopify/polaris-icons';

const getCurrentShop = (): string => {
  const pathMatch = window.location.pathname.match(/\/store\/([^\/]+)/);
  if (pathMatch && pathMatch[1]) {
    const shop = pathMatch[1];
    localStorage.setItem('current_shop', shop);
    return shop;
  }
  const urlParams = new URLSearchParams(window.location.search);
  const shopParam = urlParams.get('shop');
  if (shopParam) {
    localStorage.setItem('current_shop', shopParam);
    return shopParam;
  }
  const storedShop = localStorage.getItem('current_shop');
  if (storedShop) return storedShop;
  if ((window as any).Shopify && (window as any).Shopify.shop) {
    const shopifyShop = (window as any).Shopify.shop;
    localStorage.setItem('current_shop', shopifyShop);
    return shopifyShop;
  }
  return null;
};

const SHOP = getCurrentShop();
const API_BASE_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:5054';

interface Product {
  id: number;
  shopify_id: string;
  title: string;
  handle: string;
  description: string;
  vendor: string;
  product_type: string;
  status: string;
  published_at: string;
  price: number;
  tags: string;
  image_url: string;
  inventory_quantity: number;
  sku: string;
  collections: any;
  variants: any;
  options: any;
  images: any;
  metafields: any;
  embedding: any;
  is_enabled: number;
}

interface ProductDetail {
  id: number;
  product_id: number;
  field_name: string;
  field_value: string;
  field_type: string;
  created_at: string;
  updated_at: string;
  is_active: number;
}

interface SyncLog {
  id: number;
  synced_at: string;
  total_products: number;
  active_products: number;
  embedded_products: number;
  status: string;
  duration_seconds: number | null;
  error_message: string | null;
}

const ToggleSwitch = ({ enabled, onChange, disabled = false }: { enabled: boolean; onChange: (checked: boolean) => void; disabled?: boolean }) => (
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
    <span style={{
      position: 'absolute',
      top: '2px',
      left: enabled ? '22px' : '2px',
      width: '20px',
      height: '20px',
      background: 'white',
      borderRadius: '50%',
      transition: 'all 0.2s ease',
      boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
    }} />
  </button>
);

// Single Modal Component for Product Details + Add Info
const ProductDetailModal = ({
  product,
  open,
  onClose,
  onProductUpdated
}: {
  product: Product | null;
  open: boolean;
  onClose: () => void;
  onProductUpdated?: () => void;
}) => {
  const [selectedTab, setSelectedTab] = useState(0);
  const [productDetails, setProductDetails] = useState<ProductDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Add/Edit form state
  const [showForm, setShowForm] = useState(false);
  const [editingDetail, setEditingDetail] = useState<ProductDetail | null>(null);
  const [formData, setFormData] = useState({ field_name: '', field_value: '', field_type: 'text' });

  const fetchDetails = async (productId: number) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/product-details/${productId}?shop=${SHOP}`);
      if (response.ok) {
        const data = await response.json();
        setProductDetails(data.details || []);
      }
    } catch (err) {
      console.error('Error fetching details:', err);
    }
  };

  useEffect(() => {
    if (product?.id && open) {
      fetchDetails(product.id);
    } else if (!open) {
      setShowForm(false);
      setEditingDetail(null);
      setError(null);
      setSuccess(null);
    }
  }, [product?.id, open]);

  const polarisTabs = useMemo(() => [
    {
      id: 'basic',
      content: (<InlineStack gap="100"><Icon source={PackageIcon} tone="base" /><span>Basic Info</span></InlineStack>),
      accessibilityLabel: 'Basic Info',
      panelID: 'basic-content',
    },
    {
      id: 'inventory',
      content: (<InlineStack gap="100"><Icon source={CollectionListIcon} tone="base" /><span>Inventory</span></InlineStack>),
      accessibilityLabel: 'Inventory',
      panelID: 'inventory-content',
    },
    {
      id: 'media',
      content: (<InlineStack gap="100"><Icon source={ImageIcon} tone="base" /><span>Images</span></InlineStack>),
      accessibilityLabel: 'Images',
      panelID: 'media-content',
    },
    {
      id: 'metafields',
      content: (<InlineStack gap="100"><Icon source={DataTableIcon} tone="base" /><span>Metafields</span></InlineStack>),
      accessibilityLabel: 'Metafields',
      panelID: 'metafields-content',
    },
    {
      id: 'details',
      content: (<InlineStack gap="100"><Icon source={NoteIcon} tone="base" /><span>Additional Info</span></InlineStack>),
      accessibilityLabel: 'Additional Info',
      panelID: 'details-content',
    },
  ], []);


  const handleFieldNameChange = useCallback(
    (value: string) => setFormData(prev => ({ ...prev, field_name: value })),
    []
  );

  const handleFieldValueChange = useCallback(
    (value: string) => setFormData(prev => ({ ...prev, field_value: value })),
    []
  );

  if (!product) return null;

  const handleSaveDetail = async () => {
    if (!formData.field_name.trim() || !formData.field_value.trim()) {
      setError('Both field name and value are required');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      let response;
      if (editingDetail) {
        response = await fetch(`${API_BASE_URL}/api/product-details/${editingDetail.id}?shop=${SHOP}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            field_name: formData.field_name,
            field_value: formData.field_value,
          }),
        });
      } else {
        response = await fetch(`${API_BASE_URL}/api/product-details?shop=${SHOP}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            product_id: product.id,
            field_name: formData.field_name,
            field_value: formData.field_value,
            field_type: formData.field_type,
          }),
        });
      }

      if (response.ok) {
        setSuccess(editingDetail ? 'Detail updated successfully!' : 'Detail added successfully!');
        setShowForm(false);
        setEditingDetail(null);
        setFormData({ field_name: '', field_value: '', field_type: 'text' });
        await fetchDetails(product.id);
        if (onProductUpdated) onProductUpdated();
        setTimeout(() => setSuccess(null), 3000);
      } else {
        const data = await response.json();
        setError(data.detail || 'Failed to save detail');
      }
    } catch (err) {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteDetail = async (detailId: number) => {
    if (!confirm('Are you sure you want to delete this detail?')) return;

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/product-details/${detailId}?shop=${SHOP}&hard_delete=true`, {
        method: 'DELETE',
      });

      if (response.ok) {
        setSuccess('Detail deleted successfully!');
        await fetchDetails(product.id);
        if (onProductUpdated) onProductUpdated();
        setTimeout(() => setSuccess(null), 3000);
      }
    } catch (err) {
      setError('Failed to delete detail');
    } finally {
      setLoading(false);
    }
  };



  // Helper functions for metafields display
  const getMetafieldValue = (value: any): string => {
    if (!value) return '—';
    if (typeof value === 'string') {
      if (value.includes('gid://shopify/')) {
        const parts = value.split('/');
        return parts[parts.length - 1].replace(/["']/g, '');
      }
      return value;
    }
    if (Array.isArray(value)) return value.map(v => getMetafieldValue(v)).join(', ');
    if (typeof value === 'object' && value.value) return getMetafieldValue(value.value);
    if (typeof value === 'object') {
      if (value.name) return value.name;
      if (value.title) return value.title;
      return JSON.stringify(value);
    }
    return String(value);
  };

  const formatMetafieldKey = (key: string): string => {
    return key.split('-').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
  };

  const parseMetafields = (metafields: any) => {
    if (!metafields) return [];
    if (Array.isArray(metafields)) {
      return metafields.map(mf => ({
        key: mf.key || mf.namespace,
        value: getMetafieldValue(mf.value),
        type: mf.type || 'string',
        namespace: mf.namespace || 'custom'
      }));
    }
    if (typeof metafields === 'object') {
      return Object.entries(metafields).map(([key, value]) => ({
        key: key,
        value: getMetafieldValue(value),
        type: typeof value,
        namespace: 'custom'
      }));
    }
    return [];
  };

  const parsedMetafields = parseMetafields(product.metafields);
  const groupedMetafields = parsedMetafields.reduce((acc, mf) => {
    if (!acc[mf.namespace]) acc[mf.namespace] = [];
    acc[mf.namespace].push(mf);
    return acc;
  }, {} as Record<string, typeof parsedMetafields>);



  return (
    <Modal open={open} onClose={onClose} title={product.title} size="large" primaryAction={{ content: 'Close', onAction: onClose }}>
      <Modal.Section>
        <Tabs
          tabs={polarisTabs}
          selected={selectedTab}
          onSelect={setSelectedTab}
        />

        <Box padding="400">
          {/* Basic Info Tab */}
          {selectedTab === 0 && (
            <BlockStack gap="400">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <Card>
                  <BlockStack gap="200">
                    <Text as="h3" variant="headingSm">Basic Information</Text>
                    <Divider />
                    <BlockStack gap="100">
                      <Text as="p" variant="bodySm" tone="subdued">Title</Text>
                      <Text as="p" variant="bodyMd">{product.title}</Text>
                      <Text as="p" variant="bodySm" tone="subdued">Handle</Text>
                      <Text as="p" variant="bodyMd">{product.handle}</Text>
                      <Text as="p" variant="bodySm" tone="subdued">Vendor</Text>
                      <Text as="p" variant="bodyMd">{product.vendor || '—'}</Text>
                      <Text as="p" variant="bodySm" tone="subdued">Product Type</Text>
                      <Text as="p" variant="bodyMd">{product.product_type || '—'}</Text>
                    </BlockStack>
                  </BlockStack>
                </Card>
                <Card>
                  <BlockStack gap="200">
                    <Text as="h3" variant="headingSm">Pricing & Status</Text>
                    <Divider />
                    <BlockStack gap="100">
                      <Text as="p" variant="bodySm" tone="subdued">Price</Text>
                      <Text as="p" variant="bodyMd" fontWeight="bold">${product.price?.toFixed(2) || '0.00'}</Text>
                      <Text as="p" variant="bodySm" tone="subdued">Status</Text>
                      <Badge tone={product.status === 'active' ? 'success' : 'attention'}>{product.status}</Badge>
                      <Text as="p" variant="bodySm" tone="subdued">AI Status</Text>
                      <Badge tone={product.is_enabled === 1 ? 'success' : 'critical'}>
                        {product.is_enabled === 1 ? 'Enabled in AI' : 'Disabled in AI'}
                      </Badge>
                    </BlockStack>
                  </BlockStack>
                </Card>
              </div>
              <Card>
                <BlockStack gap="200">
                  <Text as="h3" variant="headingSm">Description</Text>
                  <Divider />
                  <div dangerouslySetInnerHTML={{ __html: product.description || 'No description' }} />
                </BlockStack>
              </Card>
              <Card>
                <BlockStack gap="200">
                  <Text as="h3" variant="headingSm">Tags</Text>
                  <Divider />
                  <InlineStack gap="100">
                    {product.tags?.split(',').map((tag, i) => (<Badge key={i} tone="info">{tag.trim()}</Badge>))}
                  </InlineStack>
                </BlockStack>
              </Card>
            </BlockStack>
          )}

          {/* Inventory Tab */}
          {selectedTab === 1 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <Card>
                <BlockStack gap="200">
                  <Text as="h3" variant="headingSm">Inventory Details</Text>
                  <Divider />
                  <BlockStack gap="100">
                    <Text as="p" variant="bodySm" tone="subdued">SKU</Text>
                    <Text as="p" variant="bodyMd">{product.sku || '—'}</Text>
                    <Text as="p" variant="bodySm" tone="subdued">Inventory Quantity</Text>
                    <Text as="p" variant="bodyMd">{product.inventory_quantity || 0}</Text>
                  </BlockStack>
                </BlockStack>
              </Card>
              <Card>
                <BlockStack gap="200">
                  <Text as="h3" variant="headingSm">Variants</Text>
                  <Divider />
                  {product.variants && product.variants.length > 0 ? (
                    <div style={{ overflowX: 'auto' }}>
                      <DataTable
                        columnContentTypes={['text', 'text', 'text', 'numeric']}
                        headings={['Variant ID', 'Title', 'SKU', 'Price']}
                        rows={product.variants.map((v: any) => [v.id, v.title || 'Default', v.sku || '—', `$${v.price || product.price}`])}
                      />
                    </div>
                  ) : (<Text tone="subdued">No variants available</Text>)}
                </BlockStack>
              </Card>
            </div>
          )}

          {/* Images Tab */}
          {selectedTab === 2 && (
            <Card>
              <BlockStack gap="200">
                <Text as="h3" variant="headingSm">Product Images</Text>
                <Divider />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '16px' }}>
                  {product.images?.filter((img: any) => img.src).map((img: any, i: number) => (
                    <div key={i} style={{ border: '1px solid #e1e3e5', borderRadius: '8px', padding: '8px', cursor: 'pointer' }}>
                      <img src={img.src} alt={img.alt || product.title} style={{ width: '100%', height: '150px', objectFit: 'cover', borderRadius: '4px' }} onClick={() => window.open(img.src, '_blank')} />
                      <Text as="p" variant="bodySm" tone="subdued" alignment="center">{img.alt || `Image ${i + 1}`}</Text>
                    </div>
                  ))}
                </div>
              </BlockStack>
            </Card>
          )}

          {/* Metafields Tab */}
          {selectedTab === 3 && (
            <Card>
              <BlockStack gap="200">
                <Text as="h3" variant="headingSm">Metafields</Text>
                <Divider />
                {Object.keys(groupedMetafields).length > 0 ? (
                  Object.entries(groupedMetafields).map(([namespace, metafieldsList]) => (
                    <Card key={namespace}>
                      <BlockStack gap="200">
                        <Text as="h4" variant="headingSm" tone="subdued">Namespace: {namespace}</Text>
                        <Divider />
                        <div style={{ overflowX: 'auto' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead><tr style={{ borderBottom: '1px solid #e1e3e5' }}>
                              <th style={{ textAlign: 'left', padding: '8px', fontWeight: 600 }}>Field</th>
                              <th style={{ textAlign: 'left', padding: '8px', fontWeight: 600 }}>Value</th>
                              <th style={{ textAlign: 'left', padding: '8px', fontWeight: 600 }}>Type</th>
                            </tr></thead>
                            <tbody>
                              {metafieldsList.map((mf, idx) => (
                                <tr key={idx} style={{ borderBottom: '1px solid #f1f2f3' }}>
                                  <td style={{ padding: '8px', verticalAlign: 'top' }}><Badge tone="info">{formatMetafieldKey(mf.key)}</Badge></td>
                                  <td style={{ padding: '8px', verticalAlign: 'top' }}><Text as="p" variant="bodyMd">{mf.value}</Text></td>
                                  <td style={{ padding: '8px', verticalAlign: 'top' }}><Badge tone="info-subdued">{mf.type}</Badge></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </BlockStack>
                    </Card>
                  ))
                ) : (<Text tone="subdued" alignment="center">No metafields available</Text>)}
              </BlockStack>
            </Card>
          )}

          {/* Additional Info Tab - with Add Info functionality inline */}
          {selectedTab === 4 && (
            <BlockStack gap="400">
              {error && <Banner tone="critical" onDismiss={() => setError(null)}>{error}</Banner>}
              {success && <Banner tone="success" onDismiss={() => setSuccess(null)}>{success}</Banner>}

              {/* Add Info Button */}
              {!showForm && (
                <InlineStack justify="end">
                  <Button onClick={() => setShowForm(true)} icon={<Icon source={PlusIcon} />}>
                    Add Additional Information
                  </Button>
                </InlineStack>
              )}

              {/* Add/Edit Form */}
              {showForm && (
                <Card>
                  <BlockStack gap="400">
                    <InlineStack align="space-between">
                      <Text as="h3" variant="headingMd">{editingDetail ? 'Edit Information' : 'Add New Information'}</Text>
                      <Button onClick={() => { setShowForm(false); setEditingDetail(null); setFormData({ field_name: '', field_value: '', field_type: 'text' }); }} size="slim">
                        Cancel
                      </Button>
                    </InlineStack>
                    <Divider />
                    <TextField
                      label="Field Name"
                      value={formData.field_name}
                      onChange={handleFieldNameChange}
                      placeholder="e.g., contraindications, storage_instructions, serving_tips"
                      autoComplete="off"
                      disabled={!!editingDetail}
                      helpText="Use underscores for spaces (e.g., serving_tips)"
                    />
                    <div>
                      <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500 }}>Field Type</label>
                      <select
                        value={formData.field_type}
                        onChange={(e) => setFormData({ ...formData, field_type: e.target.value })}
                        style={{ width: '100%', padding: '8px', borderRadius: '4px', border: '1px solid #c9cccf' }}
                        disabled={!!editingDetail}
                      >
                        <option value="text">Text</option>
                        <option value="html">HTML</option>
                        <option value="json">JSON</option>
                      </select>
                    </div>
                    <TextField
                      label="Field Value"
                      value={formData.field_value}
                      onChange={handleFieldValueChange}
                      placeholder="Enter the information..."
                      multiline={4}
                      autoComplete="off"
                    />
                    <InlineStack justify="end">
                      <Button onClick={handleSaveDetail} primary loading={loading}>
                        {editingDetail ? 'Update' : 'Save'}
                      </Button>
                    </InlineStack>
                  </BlockStack>
                </Card>
              )}

              {/* Existing Details List */}
              {productDetails.length > 0 && (
                <Card>
                  <BlockStack gap="400">
                    <Text as="h3" variant="headingMd">Existing Information</Text>
                    <Divider />
                    <div style={{ display: 'grid', gap: '16px' }}>
                      {productDetails.map((detail) => (
                        <Card key={detail.id}>
                          <InlineStack align="space-between" wrap>
                            <BlockStack gap="100">
                              <Text as="p" variant="headingSm" fontWeight="bold">
                                {detail.field_name.replace(/_/g, ' ').toUpperCase()}
                              </Text>
                              <Text as="p" variant="bodyMd">{detail.field_value}</Text>
                              <Text as="p" variant="bodySm" tone="subdued">
                                Type: {detail.field_type} | Added: {detail.created_at ? new Date(detail.created_at).toLocaleDateString() : 'Unknown'}
                              </Text>
                            </BlockStack>
                            <InlineStack gap="100">
                              <Button
                                onClick={() => {
                                  setEditingDetail(detail);
                                  setFormData({
                                    field_name: detail.field_name,
                                    field_value: detail.field_value,
                                    field_type: detail.field_type,
                                  });
                                  setShowForm(true);
                                }}
                                size="slim"
                              >
                                Edit
                              </Button>
                              <Button onClick={() => handleDeleteDetail(detail.id)} size="slim" tone="critical">
                                Delete
                              </Button>
                            </InlineStack>
                          </InlineStack>
                        </Card>
                      ))}
                    </div>
                  </BlockStack>
                </Card>
              )}

              {productDetails.length === 0 && !showForm && (
                <Card>
                  <Text tone="subdued" alignment="center">
                    No additional information added yet. Click "Add Additional Information" to add serving tips, storage instructions, contraindications, etc.
                  </Text>
                </Card>
              )}
            </BlockStack>
          )}
        </Box>
      </Modal.Section>
    </Modal>
  );
};

const PAGE_SIZE_OPTIONS = [50, 100];

export default function ProductSync() {
  const [syncingShopify, setSyncingShopify] = useState(false);
  const [syncingBrand, setSyncingBrand] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [searchValue, setSearchValue] = useState('');
  const [products, setProducts] = useState<Product[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [syncLogs, setSyncLogs] = useState<SyncLog[]>([]);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterEnabled, setFilterEnabled] = useState('all');
  const [selectedProducts, setSelectedProducts] = useState<Set<number>>(new Set());
  const [bulkActionLoading, setBulkActionLoading] = useState(false);
  const [togglingProductId, setTogglingProductId] = useState<number | null>(null);
  const [selectedProductForModal, setSelectedProductForModal] = useState<Product | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const showSuccess = (message: string) => {
    setSuccessMessage(message);
    setTimeout(() => setSuccessMessage(null), 3000);
  };

  // if (!SHOP) {
  //   return (
  //     <Page title="Product Sync Management">
  //       <div style={{ padding: '60px', textAlign: 'center' }}>
  //         <Text as="p" variant="headingLg" tone="critical">⚠️ Unable to detect Store</Text>
  //         <Text as="p" variant="bodyMd" tone="subdued" style={{ marginTop: '16px' }}>
  //           Please access this page from within your Shopify store's admin panel.
  //         </Text>
  //       </div>
  //     </Page>
  //   );
  // }

  const fetchWithTimeout = async (url: string, options?: RequestInit, timeout = 30000) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, { signal: controller.signal, ...options });
      clearTimeout(timeoutId);
      return response;
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  };

  const fetchProducts = useCallback(async () => {
    try {
      const offset = (page - 1) * pageSize;
      let url = `${API_BASE_URL}/api/products?shop=${SHOP}&limit=${pageSize}&offset=${offset}`;
      if (filterEnabled !== 'all') url += `&enabled_filter=${filterEnabled}`;
      if (filterStatus !== 'all') url += `&status=${filterStatus}`;

      const response = await fetchWithTimeout(url, 30000);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      const productsWithEnabled = (data.products || []).map((p: any) => ({
        ...p,
        is_enabled: p.is_enabled !== undefined ? p.is_enabled : 1,
        collections: typeof p.collections === 'string' ? JSON.parse(p.collections || '[]') : p.collections,
        variants: typeof p.variants === 'string' ? JSON.parse(p.variants || '[]') : p.variants,
        options: typeof p.options === 'string' ? JSON.parse(p.options || '[]') : p.options,
        images: typeof p.images === 'string' ? JSON.parse(p.images || '[]') : p.images,
        metafields: typeof p.metafields === 'string' ? JSON.parse(p.metafields || '{}') : p.metafields,
      }));
      setProducts(productsWithEnabled);
      setTotalCount(typeof data.total === 'number' ? data.total : productsWithEnabled.length);
      return true;
    } catch (err) {
      setError(`Failed to load products: ${err instanceof Error ? err.message : 'Unknown error'}`);
      return false;
    }
  }, [filterEnabled, filterStatus, page, pageSize]);

  const fetchSyncLogs = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/sync-logs?shop=${SHOP}&limit=20`, 10000);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setSyncLogs(data.logs || []);
      return true;
    } catch (err) {
      return false;
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await Promise.all([fetchProducts(), fetchSyncLogs()]);
    } catch (err) {
      setError('Failed to load data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [fetchProducts, fetchSyncLogs]);

  useEffect(() => { loadData(); }, [loadData]);

  // Sync runs can take minutes for large catalogs — far longer than any
  // sane HTTP/proxy timeout. The endpoints kick the job off in the
  // background and return immediately with a sync_log_id; we poll
  // /api/sync-logs until that run finishes instead of holding the request open.
  const pollSyncLog = async (syncLogId: number, maxAttempts = 200, intervalMs = 3000): Promise<any> => {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      await new Promise(resolve => setTimeout(resolve, intervalMs));
      try {
        const response = await fetchWithTimeout(`${API_BASE_URL}/api/sync-logs?shop=${SHOP}&limit=10`, undefined, 15000);
        if (response.ok) {
          const data = await response.json();
          const log = (data.logs || []).find((l: any) => l.id === syncLogId);
          if (log && log.status !== 'running') return log;
        }
      } catch {
        // transient polling error — keep retrying until maxAttempts
      }
    }
    throw new Error('Sync is taking longer than expected. Check Sync History below for the final result.');
  };

  const handleShopifySync = async () => {
    setSyncingShopify(true);
    setError(null);
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/sync-products?shop=${SHOP}`, undefined, 15000);
      if (!response.ok) throw new Error(`Sync failed to start: ${response.status}`);
      const data = await response.json();
      showSuccess('Shopify product sync started — this can take a few minutes for large catalogs.');

      const log = await pollSyncLog(data.sync_log_id);
      if (log.status === 'success') {
        showSuccess(log.error_message || 'Shopify products synced successfully!');
      } else {
        setError(`Shopify sync failed: ${log.error_message || 'Unknown error'}`);
      }
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Shopify sync failed. Please try again.');
    } finally {
      setSyncingShopify(false);
    }
  };

  const handleBrandSync = async () => {
    setSyncingBrand(true);
    setError(null);
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/sync/international-to-pinecone?shop=${SHOP}`, undefined, 15000);
      if (!response.ok) throw new Error(`Sync failed to start: ${response.status}`);
      const data = await response.json();
      showSuccess('Brand/International product sync started — this can take a few minutes.');

      const log = await pollSyncLog(data.sync_log_id);
      if (log.status === 'success') {
        showSuccess(log.error_message || 'Brand/International products synced successfully!');
      } else {
        setError(`Brand/International sync failed: ${log.error_message || 'Unknown error'}`);
      }
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Brand/International sync failed. Please try again.');
    } finally {
      setSyncingBrand(false);
    }
  };

  const toggleProductEnabled = async (productId: number, currentStatus: number) => {
    const newStatus = currentStatus === 1 ? 0 : 1;
    setTogglingProductId(productId);
    const originalProducts = [...products];
    setProducts(prev => prev.map(p => p.id === productId ? { ...p, is_enabled: newStatus } : p));

    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/products/${productId}/toggle-enabled?shop=${SHOP}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_enabled: newStatus }),
      }, 10000);
      if (!response.ok) throw new Error('Failed to update');
      showSuccess(`Product ${newStatus === 1 ? 'enabled' : 'disabled'} in AI`);
    } catch (err) {
      setProducts(originalProducts);
      setError(`Failed to ${newStatus === 1 ? 'enable' : 'disable'} product`);
    } finally {
      setTogglingProductId(null);
    }
  };

  const bulkToggleProducts = async (enable: boolean) => {
    if (selectedProducts.size === 0) { setError('Please select at least one product'); return; }
    setBulkActionLoading(true);
    const productIds = Array.from(selectedProducts);
    const isEnabledValue = enable ? 1 : 0;
    const originalProducts = [...products];
    setProducts(prev => prev.map(p => selectedProducts.has(p.id) ? { ...p, is_enabled: isEnabledValue } : p));

    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/api/products/bulk-toggle-enabled?shop=${SHOP}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_ids: productIds, is_enabled: isEnabledValue }),
      }, 15000);
      if (!response.ok) throw new Error('Bulk update failed');
      showSuccess(`${productIds.length} products ${enable ? 'enabled' : 'disabled'} in AI`);
      setSelectedProducts(new Set());
    } catch (err) {
      setProducts(originalProducts);
      setError(`Failed to ${enable ? 'enable' : 'disable'} products`);
    } finally {
      setBulkActionLoading(false);
    }
  };

  const handleSelectProduct = (productId: number, checked: boolean) => {
    const newSelected = new Set(selectedProducts);
    checked ? newSelected.add(productId) : newSelected.delete(productId);
    setSelectedProducts(newSelected);
  };

  const handleSelectAll = (checked: boolean) => {
    setSelectedProducts(checked ? new Set(filteredProducts.map(p => p.id)) : new Set());
  };

  const openProductDetail = (product: Product) => {
    setSelectedProductForModal(product);
    setModalOpen(true);
  };

  const filteredProducts = products.filter(product => {
    const matchesSearch = searchValue === '' ||
      product.title?.toLowerCase().includes(searchValue.toLowerCase()) ||
      product.sku?.toLowerCase().includes(searchValue.toLowerCase()) ||
      product.product_type?.toLowerCase().includes(searchValue.toLowerCase());
    const matchesStatus = filterStatus === 'all' || product.status === filterStatus;
    const matchesEnabled = filterEnabled === 'all' ||
      (filterEnabled === 'enabled' && product.is_enabled === 1) ||
      (filterEnabled === 'disabled' && product.is_enabled === 0);
    return matchesSearch && matchesStatus && matchesEnabled;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active': return <Badge tone="success">Active</Badge>;
      case 'draft': return <Badge tone="attention">Draft</Badge>;
      default: return <Badge>{status || 'Unknown'}</Badge>;
    }
  };

  const totalProducts = totalCount;
  const enabledInAI = products.filter(p => p.is_enabled === 1).length;
  const activeCount = products.filter(p => p.status === 'active').length;
  const draftCount = products.filter(p => p.status === 'draft').length;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  const productRows = filteredProducts.map(product => [
    <div key={`select-${product.id}`}>
      <Checkbox label="" checked={selectedProducts.has(product.id)} onChange={(checked) => handleSelectProduct(product.id, checked)} />
    </div>,
    <div key={`product-${product.id}`} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      {product.image_url ? (
        <img src={product.image_url} alt={product.title} style={{ width: '50px', height: '50px', objectFit: 'cover', borderRadius: '8px', cursor: 'pointer' }} onClick={() => openProductDetail(product)} />
      ) : (
        <div style={{ width: '50px', height: '50px', background: '#f1f2f3', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={() => openProductDetail(product)}>
          <Icon source={PackageIcon} tone="subdued" />
        </div>
      )}
      <BlockStack gap="050">
        <Button onClick={() => openProductDetail(product)} variant="plain">
          <Text as="p" variant="bodyMd" fontWeight="medium">{product.title || 'Untitled'}</Text>
        </Button>
        <Text as="p" variant="bodySm" tone="subdued">SKU: {product.sku || 'N/A'}</Text>
      </BlockStack>
    </div>,
    product.product_type || 'Uncategorized',
    product.vendor || '—',
    `$${product.price?.toFixed(2) || '0.00'}`,
    product.inventory_quantity || 0,
    getStatusBadge(product.status),
    <div key={`toggle-${product.id}`} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <ToggleSwitch enabled={product.is_enabled === 1} onChange={() => toggleProductEnabled(product.id, product.is_enabled)} disabled={syncingShopify || syncingBrand || bulkActionLoading || togglingProductId === product.id} />
      <span style={{ fontSize: '12px', color: product.is_enabled === 1 ? '#008060' : '#8a8f96' }}>{product.is_enabled === 1 ? 'ON' : 'OFF'}</span>
    </div>,
  ]);

  const formatDate = (isoString: string) => {
    try { return new Date(isoString).toLocaleString(); } catch { return isoString; }
  };

  const syncLogRows = syncLogs.map(log => [
    formatDate(log.synced_at),
    log.total_products || 0,
    log.active_products || 0,
    log.embedded_products || 0,
    log.duration_seconds ? `${log.duration_seconds.toFixed(1)}s` : '—',
    <Badge key={`status-${log.id}`} tone={log.status === 'success' ? 'success' : log.status === 'running' ? 'info' : 'critical'}>{log.status}</Badge>,
  ]);

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spinner size="large" /></div>;
  }

  return (
    <Page
      title="Product Sync Management"
      subtitle="Sync your Shopify products with the AI assistant"
    >
      <Layout>
        <Layout.Section>
          <BlockStack gap="500">
            <Card>
              <InlineStack align="space-between" blockAlign="center" wrap>
                <Text as="p" variant="bodyMd" tone="subdued">Run a sync to pick up new or changed products.</Text>
                <InlineStack gap="200">
                  <Button onClick={handleShopifySync} loading={syncingShopify} disabled={syncingShopify || syncingBrand} icon={<Icon source={RefreshIcon} />}>
                    {syncingShopify ? 'Syncing Shopify Products...' : 'Shopify Product Sync'}
                  </Button>
                  <Button onClick={handleBrandSync} loading={syncingBrand} disabled={syncingShopify || syncingBrand} icon={<Icon source={RefreshIcon} />}>
                    {syncingBrand ? 'Syncing Brand Products...' : 'Brand/International Product Sync'}
                  </Button>
                </InlineStack>
              </InlineStack>
            </Card>

            {error && <Banner tone="critical" onDismiss={() => setError(null)}><BlockStack gap="200"><Text as="p">{error}</Text><Button onClick={loadData} size="slim">Retry</Button></BlockStack></Banner>}
            {successMessage && <Banner tone="success" onDismiss={() => setSuccessMessage(null)}>{successMessage}</Banner>}

            {selectedProducts.size > 0 && (
              <Card>
                <InlineStack align="space-between" blockAlign="center">
                  <Text as="p" variant="bodyMd"><strong>{selectedProducts.size}</strong> product{selectedProducts.size !== 1 ? 's' : ''} selected</Text>
                  <InlineStack gap="200">
                    <Button onClick={() => bulkToggleProducts(true)} loading={bulkActionLoading} disabled={bulkActionLoading}>✓ Enable in AI</Button>
                    <Button onClick={() => bulkToggleProducts(false)} loading={bulkActionLoading} disabled={bulkActionLoading} tone="critical">✗ Disable in AI</Button>
                    <Button onClick={() => setSelectedProducts(new Set())}>Clear Selection</Button>
                  </InlineStack>
                </InlineStack>
              </Card>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px' }}>
              <Card><BlockStack gap="200"><InlineStack gap="200" blockAlign="center"><div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #008060 0%, #00a075 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Icon source={PackageIcon} tone="base" /></div><BlockStack gap="050"><Text as="p" variant="bodySm" tone="subdued">Total Products</Text><Text as="p" variant="heading2xl">{totalProducts}</Text><Text as="p" variant="bodySm" tone="subdued">{enabledInAI} in AI</Text></BlockStack></InlineStack></BlockStack></Card>
              <Card><BlockStack gap="200"><InlineStack gap="200" blockAlign="center"><div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #5c6ac4 0%, #7b8ad4 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Icon source={ContentIcon} tone="base" /></div><BlockStack gap="050"><Text as="p" variant="bodySm" tone="subdued">Shopify Status</Text><Text as="p" variant="heading2xl">{activeCount}</Text><Text as="p" variant="bodySm" tone="subdued">Active • {draftCount} draft</Text></BlockStack></InlineStack></BlockStack></Card>
              <Card><BlockStack gap="200"><InlineStack gap="200" blockAlign="center"><div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #e86339 0%, #ff8a5c 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Icon source={DatabaseIcon} tone="base" /></div><BlockStack gap="050"><Text as="p" variant="bodySm" tone="subdued">AI Availability</Text><Text as="p" variant="heading2xl">{enabledInAI}</Text><Text as="p" variant="bodySm" tone="subdued">Products in AI search</Text></BlockStack></InlineStack></BlockStack></Card>
            </div>

            <Card>
              <BlockStack gap="400">
                <InlineStack align="space-between" blockAlign="start">
                  <BlockStack gap="100">
                    <Text as="h2" variant="headingLg">Product Catalog</Text>
                    <Text as="p" variant="bodySm" tone="subdued">
                      Showing {products.length === 0 ? 0 : (page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount} products
                    </Text>
                  </BlockStack>
                  <InlineStack gap="200">
                    <select value={filterEnabled} onChange={(e) => { setFilterEnabled(e.target.value); setSelectedProducts(new Set()); setPage(1); }} style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #c9cccf', background: 'white', fontSize: '14px', cursor: 'pointer' }}>
                      <option value="all">All (AI Status)</option>
                      <option value="enabled">✓ Enabled in AI</option>
                      <option value="disabled">✗ Disabled in AI</option>
                    </select>
                    <select value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setSelectedProducts(new Set()); setPage(1); }} style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #c9cccf', background: 'white', fontSize: '14px', cursor: 'pointer' }}>
                      <option value="all">All Status</option>
                      <option value="active">Active</option>
                      <option value="draft">Draft</option>
                    </select>
                    <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid #c9cccf', background: 'white', fontSize: '14px', cursor: 'pointer' }}>
                      {PAGE_SIZE_OPTIONS.map(size => (
                        <option key={size} value={size}>{size} / page</option>
                      ))}
                    </select>
                    <div style={{ width: '260px' }}>
                      <TextField label="Search products" labelHidden value={searchValue} onChange={setSearchValue} placeholder="Search this page..." autoComplete="off" clearButton onClearButtonClick={() => setSearchValue('')} prefix={<Icon source={SearchIcon} tone="base" />} />
                    </div>
                  </InlineStack>
                </InlineStack>
                <InlineStack align="end"><Checkbox label="Select All" checked={selectedProducts.size === filteredProducts.length && filteredProducts.length > 0} onChange={handleSelectAll} indeterminate={selectedProducts.size > 0 && selectedProducts.size < filteredProducts.length} /></InlineStack>
                {productRows.length > 0 ? (
                  <div style={{ overflowX: 'auto' }}>
                    <DataTable columnContentTypes={['text', 'text', 'text', 'text', 'text', 'numeric', 'text', 'text', 'text']} headings={['Select', 'Product', 'Category', 'Vendor', 'Price', 'Inventory', 'Status', 'AI Status']} rows={productRows} hoverable />
                  </div>
                ) : (<Box padding="400"><Text tone="subdued" alignment="center">No products found matching your criteria.</Text></Box>)}
                <InlineStack align="center" gap="300" blockAlign="center">
                  <Button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>Previous</Button>
                  <Text as="span" variant="bodySm" tone="subdued">Page {page} of {totalPages}</Text>
                  <Button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>Next</Button>
                </InlineStack>
              </BlockStack>
            </Card>

            {syncLogRows.length > 0 && (
              <Card>
                <BlockStack gap="400">
                  <Text as="h2" variant="headingLg">Sync History</Text>
                  <div style={{ overflowX: 'auto' }}>
                    <DataTable columnContentTypes={['text', 'numeric', 'numeric', 'numeric', 'text', 'text']} headings={['Date', 'Total', 'Active', 'Embedded', 'Duration', 'Status']} rows={syncLogRows} hoverable />
                  </div>
                </BlockStack>
              </Card>
            )}
          </BlockStack>
        </Layout.Section>
      </Layout>

      <ProductDetailModal
        product={selectedProductForModal}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onProductUpdated={loadData}
      />
    </Page>
  );
}