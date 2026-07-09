import { Select } from '@shopify/polaris';
import { useState, useCallback } from 'react';

export function PineConeAutoComplete({ value, onChange }) {

    return (
        <Select
            label="Pinecone Environment / Region"
            options={[
                { label: 'Select region', value: '' },
                { label: 'us-east-1', value: 'us-east-1' },
                { label: 'us-west-2', value: 'us-west-2' },
                { label: 'eu-west-1', value: 'eu-west-1' },
            ]}
            value={value}
            onChange={onChange}
        />
    );
}
