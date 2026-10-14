import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import Dropdown from '@/design-system/Dropdown';
import DropdownItem from '@/design-system/DropdownItem';

const VersionDropdown = () => {
    const [selectedVersion, setSelectedVersion] = useState('v1');

    const versions = [
        { id: 'v1', name: 'V1.0.0', description: 'Planner-based BookShelf', url: null }, // Current page
        { id: 'legacy-2', name: 'Legacy 2', description: 'Smart filters to parse query', url: 'https://tuanqpham0921.com/book-recommender-v2' },
        { id: 'legacy-1', name: 'Legacy 1', description: 'Pre-defined filters and limited', url: 'https://tuanqpham0921.com/book-recommender-v1' },
    ];

    const handleVersionSelect = (version, close) => {
        setSelectedVersion(version.id);
        close();

        // Navigate to the legacy apps, stay on the current page for V1
        if (version.url) {
            window.location.href = version.url;
        }
    };

    return (
        <Dropdown
            panelClassName="w-56 rounded-b-2xl rounded-tr-2xl"
            trigger={({ toggle }) => (
                <button
                    onClick={toggle}
                    className="underline-animated underline-button flex items-center"
                >
                    Version 1
                    <ChevronDown size={16} className="text-[var(--text-inactive)] ml-1 mt-1" />
                </button>
            )}
        >
            {({ close }) => versions.map((version) => (
                <DropdownItem
                    key={version.id}
                    onClick={() => handleVersionSelect(version, close)}
                    selected={version.id === selectedVersion}
                >
                    <div className="flex items-center justify-between">
                        <div className="flex flex-col text-left">
                            <span className="text-left text-small">{version.name}</span>
                            <span className="text-xs text-[var(--text-inactive)] font-normal text-left">{version.description}</span>
                        </div>
                        {version.id === selectedVersion && (
                            <span className="text-[var(--text-hover)] ml-3">✓</span>
                        )}
                    </div>
                </DropdownItem>
            ))}
        </Dropdown>
    );
};

export default VersionDropdown;
