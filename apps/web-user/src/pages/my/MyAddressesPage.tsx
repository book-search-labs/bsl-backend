import { useEffect, useState } from 'react'

import { createAddress, listAddresses, setDefaultAddress, updateAddress, type Address } from '../../api/checkout'

type AddressForm = {
  name: string
  phone: string
  zip: string
  addr1: string
  addr2: string
}

const LOCAL_ADDRESS_KEY = 'bsl.my.addresses.fallback'

function readFallbackAddresses() {
  const raw = localStorage.getItem(LOCAL_ADDRESS_KEY)
  if (!raw) return [] as Address[]
  try {
    return JSON.parse(raw) as Address[]
  } catch {
    return [] as Address[]
  }
}

function writeFallbackAddresses(items: Address[]) {
  localStorage.setItem(LOCAL_ADDRESS_KEY, JSON.stringify(items))
}

export default function MyAddressesPage() {
  const [items, setItems] = useState<Address[]>([])
  const [useFallback, setUseFallback] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [editingAddressId, setEditingAddressId] = useState<number | null>(null)
  const [form, setForm] = useState<AddressForm>({ name: '', phone: '', zip: '', addr1: '', addr2: '' })

  useEffect(() => {
    let active = true

    listAddresses()
      .then((data) => {
        if (!active) return
        setItems(data)
      })
      .catch(() => {
        if (!active) return
        setUseFallback(true)
        setItems(readFallbackAddresses())
      })

    return () => {
      active = false
    }
  }, [])

  const resetForm = () => {
    setForm({ name: '', phone: '', zip: '', addr1: '', addr2: '' })
    setEditingAddressId(null)
  }

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.phone.trim() || !form.addr1.trim()) {
      setNotice('받는 분, 연락처, 기본 주소를 입력해 주세요.')
      return
    }

    const isEditing = editingAddressId !== null

    if (useFallback) {
      if (isEditing) {
        const next = items.map((item) =>
          item.address_id === editingAddressId
            ? {
                ...item,
                name: form.name.trim(),
                phone: form.phone.trim(),
                zip: form.zip.trim(),
                addr1: form.addr1.trim(),
                addr2: form.addr2.trim(),
              }
            : item,
        )
        setItems(next)
        writeFallbackAddresses(next)
        setNotice('배송지가 수정되었습니다. (로컬 저장)')
        resetForm()
        return
      }

      const fallbackItem: Address = {
        address_id: Date.now(),
        name: form.name.trim(),
        phone: form.phone.trim(),
        zip: form.zip.trim(),
        addr1: form.addr1.trim(),
        addr2: form.addr2.trim(),
        is_default: items.length === 0,
      }
      const next = [fallbackItem, ...items]
      setItems(next)
      writeFallbackAddresses(next)
      setNotice('배송지가 등록되었습니다. (로컬 저장)')
      resetForm()
      return
    }

    try {
      if (isEditing) {
        const address = await updateAddress(editingAddressId, {
          name: form.name.trim(),
          phone: form.phone.trim(),
          zip: form.zip.trim(),
          addr1: form.addr1.trim(),
          addr2: form.addr2.trim(),
        })
        setItems((prev) => prev.map((item) => (item.address_id === address.address_id ? address : item)))
        setNotice('배송지가 수정되었습니다.')
      } else {
        const address = await createAddress({
          name: form.name.trim(),
          phone: form.phone.trim(),
          zip: form.zip.trim(),
          addr1: form.addr1.trim(),
          addr2: form.addr2.trim(),
          isDefault: items.length === 0,
        })
        setItems((prev) => [address, ...prev])
        setNotice('배송지가 등록되었습니다.')
      }
      resetForm()
    } catch (err) {
      setNotice(err instanceof Error ? err.message : isEditing ? '배송지 수정에 실패했습니다.' : '배송지 등록에 실패했습니다.')
    }
  }

  const handleEdit = (address: Address) => {
    setNotice(null)
    setEditingAddressId(address.address_id)
    setForm({
      name: address.name ?? '',
      phone: address.phone ?? '',
      zip: address.zip ?? '',
      addr1: address.addr1 ?? '',
      addr2: address.addr2 ?? '',
    })
  }

  const handleSetDefault = async (addressId: number) => {
    if (useFallback) {
      const next = items.map((item) => ({ ...item, is_default: item.address_id === addressId }))
      setItems(next)
      writeFallbackAddresses(next)
      setNotice('기본 배송지를 변경했습니다. (로컬 저장)')
      return
    }

    try {
      const updated = await setDefaultAddress(addressId)
      setItems((prev) => prev.map((item) => ({ ...item, is_default: item.address_id === updated.address_id })))
      setNotice('기본 배송지를 변경했습니다.')
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '기본 배송지 변경에 실패했습니다.')
    }
  }

  return (
    <section className="my-content-section">
      <header className="my-section-header">
        <h1>배송 주소록</h1>
        <p>자주 사용하는 배송지를 저장해 주문 시 빠르게 선택할 수 있습니다.</p>
      </header>

      <section className="my-panel">
        <h2 className="my-subtitle">{editingAddressId ? '배송지 수정' : '배송지 추가'}</h2>
        <div className="my-form-grid">
          <label>
            받는 분
            <input value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} />
          </label>
          <label>
            연락처
            <input
              value={form.phone}
              onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
            />
          </label>
          <label>
            우편번호
            <input value={form.zip} onChange={(event) => setForm((prev) => ({ ...prev, zip: event.target.value }))} />
          </label>
          <label>
            기본 주소
            <input
              value={form.addr1}
              onChange={(event) => setForm((prev) => ({ ...prev, addr1: event.target.value }))}
            />
          </label>
          <label>
            상세 주소
            <input
              value={form.addr2}
              onChange={(event) => setForm((prev) => ({ ...prev, addr2: event.target.value }))}
            />
          </label>
          <div className="d-flex gap-2">
            <button type="button" className="btn btn-primary align-self-start" onClick={handleSubmit}>
              {editingAddressId ? '배송지 수정' : '배송지 등록'}
            </button>
            {editingAddressId ? (
              <button type="button" className="btn btn-outline-secondary align-self-start" onClick={resetForm}>
                수정 취소
              </button>
            ) : null}
          </div>
          {notice ? <div className="my-notice">{notice}</div> : null}
        </div>
      </section>

      <section className="my-panel mt-4">
        <h2 className="my-subtitle">등록된 배송지</h2>
        {items.length === 0 ? <div className="my-empty">등록된 배송지가 없습니다.</div> : null}
        {items.length > 0 ? (
          <div className="my-list-table">
            {items.map((item) => (
              <div key={item.address_id} className="my-list-row">
                <div>
                  <div className="my-list-title">{item.name}</div>
                  <div className="my-list-sub">
                    {item.zip ?? '-'} {item.addr1 ?? ''} {item.addr2 ?? ''}
                  </div>
                  <div className="my-list-sub">{item.phone}</div>
                </div>
                <div className="my-list-meta">{item.is_default ? '기본 배송지' : ''}</div>
                <div className="d-flex gap-2">
                  <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => handleEdit(item)}>
                    수정
                  </button>
                  <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => handleSetDefault(item.address_id)}>
                    기본 설정
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </section>
  )
}
